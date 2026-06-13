import json
import mimetypes
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymysql
import requests
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
UPLOAD_DIR = ROOT / "uploads"
ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf"}


def load_env(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env(ROOT / ".env")


CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "creoianw_bhasin"),
    "table": os.getenv("DB_TABLE", "waba"),
    "server_host": os.getenv("APP_HOST", "127.0.0.1"),
    "server_port": int(os.getenv("APP_PORT") or os.getenv("PYTHON_PORT") or "9010"),
    "public_base_url": os.getenv("PUBLIC_BASE_URL", "https://10.1.1.150:9010"),
    "whatsapp_provider": os.getenv("WHATSAPP_PROVIDER", "disabled"),
    "netcore_url": os.getenv("NETCORE_URL", "https://waapi.pepipost.com/api/v2/message/"),
    "netcore_image_url": os.getenv("NETCORE_IMAGE_URL", "https://cpaaswa.netcorecloud.net/api/v2/message/nc"),
    "netcore_media_url": os.getenv("NETCORE_MEDIA_URL", "https://cpaaswa.netcorecloud.net/api/v2/media"),
    "netcore_token": os.getenv("NETCORE_TOKEN", ""),
    "netcore_source": os.getenv("NETCORE_SOURCE", ""),
    "netcore_image_template": os.getenv("NETCORE_IMAGE_TEMPLATE", "media_template_image"),
    "stewindia_url": os.getenv("STEWINDIA_URL", "http://mediaapi.stewindia.com/api/sendText"),
    "stewindia_token": os.getenv("STEWINDIA_TOKEN", ""),
    "lead_db_host": os.getenv("LEAD_DB_HOST", ""),
    "lead_db_port": int(os.getenv("LEAD_DB_PORT", "3306")),
    "lead_db_name": os.getenv("LEAD_DB_NAME", ""),
    "lead_db_user": os.getenv("LEAD_DB_USER", ""),
    "lead_db_password": os.getenv("LEAD_DB_PASSWORD", ""),
    "ssl_cert_file": os.getenv("SSL_CERT_FILE", ""),
    "ssl_key_file": os.getenv("SSL_KEY_FILE", ""),
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.secret_key = os.getenv("APP_SECRET_KEY", "arpra-prototype-local-secret")


SEED_USERS = [
    ("suresh", "Suresh Kundra", "suresh123", "agent"),
    ("frontdesk", "Front Desk", "front123", "agent"),
    ("admin", "ARPRA Admin", "admin123", "admin"),
]


def quote_identifier(value):
    return f"`{str(value).replace('`', '``')}`"


def db_connection(database=True):
    options = {
        "host": CONFIG["host"],
        "port": CONFIG["port"],
        "user": CONFIG["user"],
        "password": CONFIG["password"],
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }
    if database:
        options["database"] = CONFIG["database"]
    return pymysql.connect(**options)


def lead_db_connection():
    if not CONFIG["lead_db_host"] or not CONFIG["lead_db_name"] or not CONFIG["lead_db_user"]:
        raise ValueError("Lead DB is not configured")
    return pymysql.connect(
        host=CONFIG["lead_db_host"],
        port=CONFIG["lead_db_port"],
        user=CONFIG["lead_db_user"],
        password=CONFIG["lead_db_password"],
        database=CONFIG["lead_db_name"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=5,
    )


def log_line(file_name, message, **data):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(), "message": message, **data}
    with (LOG_DIR / file_name).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def mask_mobile(value):
    text = str(value or "")
    return text if len(text) <= 4 else f"{'*' * (len(text) - 4)}{text[-4:]}"


def public_url(path):
    return f"{CONFIG['public_base_url'].rstrip('/')}/{str(path).lstrip('/')}"


def upload_kind(filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        return ""
    return "document" if extension == "pdf" else "image"


def media_url(value):
    text = str(value or "").strip()
    return text if text.startswith(("http://", "https://", "/uploads/")) else ""


def normalize_media(data):
    media = data.get("media") if isinstance(data.get("media"), dict) else {}
    url = str(media.get("url") or data.get("media_url") or "").strip()
    filename = secure_filename(str(media.get("filename") or data.get("filename") or "").strip())[:225]
    kind = str(media.get("kind") or data.get("media_kind") or "").strip().lower()
    if not kind and filename:
        kind = upload_kind(filename)
    if not kind and url:
        kind = "document" if url.lower().split("?", 1)[0].endswith(".pdf") else "image"
    if kind not in {"image", "document"}:
        kind = ""
    return {"kind": kind, "url": url, "filename": filename or Path(url).name[:225]}


def ensure_column(cursor, column_name, definition):
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (CONFIG["database"], CONFIG["table"], column_name),
    )
    if not cursor.fetchone()["total"]:
        cursor.execute(
            f"ALTER TABLE {quote_identifier(CONFIG['table'])} "
            f"ADD COLUMN {quote_identifier(column_name)} {definition}"
        )


def ensure_column_definition(cursor, column_name, definition):
    ensure_column(cursor, column_name, definition)
    cursor.execute(
        f"ALTER TABLE {quote_identifier(CONFIG['table'])} "
        f"MODIFY COLUMN {quote_identifier(column_name)} {definition}"
    )


def ensure_index_columns(cursor, database_name, table_name, index_name, column_names):
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s
        """,
        (database_name, table_name, index_name),
    )
    if cursor.fetchone()["total"]:
        return
    columns_sql = ", ".join(quote_identifier(column) for column in column_names)
    cursor.execute(
        f"ALTER TABLE {quote_identifier(database_name)}.{quote_identifier(table_name)} "
        f"ADD INDEX {quote_identifier(index_name)} ({columns_sql})"
    )


def init_db():
    with db_connection(database=False) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {quote_identifier(CONFIG['database'])} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )

    table = quote_identifier(CONFIG["table"])
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  mobile VARCHAR(45) NOT NULL,
                  msg TEXT NOT NULL,
                  img TEXT NOT NULL,
                  vedio TEXT NOT NULL,
                  pdff VARCHAR(225) NOT NULL,
                  docid TEXT NOT NULL,
                  imgid TEXT NOT NULL,
                  wabadatetime VARCHAR(225) NOT NULL,
                  empname VARCHAR(225) NOT NULL,
                  datetimess DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  color VARCHAR(225) NOT NULL,
                  status INT NOT NULL DEFAULT 0,
                  empnamestatus VARCHAR(225) NOT NULL,
                  datetimesnot VARCHAR(225) NOT NULL,
                  provider_message_id VARCHAR(191) NULL,
                  delivery_status VARCHAR(80) NULL,
                  delivery_status_remark TEXT NULL,
                  delivery_received_at VARCHAR(80) NULL,
                  INDEX idx_waba_mobile_date (mobile, datetimess),
                  INDEX idx_waba_date (datetimess),
                  INDEX idx_waba_provider_message_id (provider_message_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            ensure_column(cursor, "provider_message_id", "VARCHAR(191) NULL")
            ensure_column(cursor, "delivery_status", "VARCHAR(80) NULL")
            ensure_column(cursor, "delivery_status_remark", "TEXT NULL")
            ensure_column(cursor, "delivery_received_at", "VARCHAR(80) NULL")
            ensure_column_definition(cursor, "docid", "TEXT NOT NULL")
            ensure_column_definition(cursor, "imgid", "TEXT NOT NULL")
            ensure_index_columns(cursor, CONFIG["database"], CONFIG["table"], "idx_waba_provider_message_id", ["provider_message_id"])
            ensure_index_columns(cursor, CONFIG["database"], CONFIG["table"], "idx_waba_date_mobile_id", ["datetimess", "mobile", "id"])
            ensure_index_columns(cursor, CONFIG["database"], CONFIG["table"], "idx_waba_mobile_id", ["mobile", "id"])
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS incoming_webhook_logs (
                  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  mobile VARCHAR(45) NULL,
                  received_at VARCHAR(80) NULL,
                  payload_json LONGTEXT NOT NULL,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX idx_incoming_mobile (mobile),
                  INDEX idx_incoming_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_webhook_logs (
                  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  provider_message_id VARCHAR(191) NULL,
                  status VARCHAR(80) NULL,
                  status_remark TEXT NULL,
                  received_at VARCHAR(80) NULL,
                  payload_json LONGTEXT NOT NULL,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX idx_delivery_provider_message_id (provider_message_id),
                  INDEX idx_delivery_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  username VARCHAR(80) NOT NULL UNIQUE,
                  display_name VARCHAR(120) NOT NULL,
                  password_hash VARCHAR(255) NOT NULL,
                  role VARCHAR(40) NOT NULL DEFAULT 'agent',
                  is_active TINYINT(1) NOT NULL DEFAULT 1,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX idx_users_active_name (is_active, display_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_state (
                  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  mobile VARCHAR(45) NOT NULL UNIQUE,
                  owner_user_id INT NULL,
                  owner_name VARCHAR(120) NULL,
                  conversation_type VARCHAR(80) NULL,
                  status VARCHAR(40) NOT NULL DEFAULT 'open',
                  closed_by_user_id INT NULL,
                  closed_by_name VARCHAR(120) NULL,
                  closed_at DATETIME NULL,
                  closure_note TEXT NULL,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  INDEX idx_state_owner (owner_user_id),
                  INDEX idx_state_status (status),
                  INDEX idx_state_type (conversation_type),
                  CONSTRAINT fk_state_owner FOREIGN KEY (owner_user_id) REFERENCES users(id),
                  CONSTRAINT fk_state_closed_by FOREIGN KEY (closed_by_user_id) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_actions (
                  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  mobile VARCHAR(45) NOT NULL,
                  action_type VARCHAR(80) NOT NULL,
                  performed_by_user_id INT NULL,
                  performed_by_name VARCHAR(120) NOT NULL,
                  old_owner_user_id INT NULL,
                  old_owner_name VARCHAR(120) NULL,
                  new_owner_user_id INT NULL,
                  new_owner_name VARCHAR(120) NULL,
                  old_value TEXT NULL,
                  new_value TEXT NULL,
                  reason TEXT NULL,
                  payload_json LONGTEXT NULL,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX idx_actions_mobile_created (mobile, created_at),
                  INDEX idx_actions_type (action_type),
                  INDEX idx_actions_new_owner (new_owner_user_id),
                  CONSTRAINT fk_actions_performed_by FOREIGN KEY (performed_by_user_id) REFERENCES users(id),
                  CONSTRAINT fk_actions_old_owner FOREIGN KEY (old_owner_user_id) REFERENCES users(id),
                  CONSTRAINT fk_actions_new_owner FOREIGN KEY (new_owner_user_id) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_notes (
                  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  mobile VARCHAR(45) NOT NULL,
                  note TEXT NOT NULL,
                  created_by_user_id INT NULL,
                  created_by_name VARCHAR(120) NOT NULL,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX idx_notes_mobile_created (mobile, created_at),
                  CONSTRAINT fk_notes_created_by FOREIGN KEY (created_by_user_id) REFERENCES users(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            for username, display_name, password, role in SEED_USERS:
                cursor.execute(
                    """
                    INSERT INTO users (username, display_name, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      display_name = VALUES(display_name),
                      role = VALUES(role),
                      is_active = 1
                    """,
                    (username, display_name, generate_password_hash(password), role),
                )


def display_date(value=None):
    dt = value or datetime.now()
    return dt.strftime("%d/%m/%Y, %I:%M %p")


def parse_payload_date(value):
    if value is None:
        return datetime.now()
    text = str(value)
    if text.isdigit():
        timestamp = int(text)
        if len(text) <= 10:
            timestamp *= 1000
        return datetime.fromtimestamp(timestamp / 1000)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except ValueError:
        return datetime.now()


def day_bounds(date_text):
    day = datetime.strptime(date_text, "%Y-%m-%d")
    next_day = day + timedelta(days=1)
    return day.strftime("%Y-%m-%d 00:00:00"), next_day.strftime("%Y-%m-%d 00:00:00")


def today_bounds():
    return day_bounds(datetime.now().strftime("%Y-%m-%d"))


def normalize_mobile(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit() or ch == "-")[:45]


def phone_digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def phone_variants(value):
    digits = phone_digits(value)
    if not digits:
        return set()
    meaningful = digits[-10:] if len(digits) >= 10 else digits
    variants = {digits, meaningful}
    if len(digits) > 10:
        variants.add(digits[-10:])
    if len(meaningful) == 10:
        variants.add(f"91{meaningful}")
    return {item for item in variants if item}


def mobile_clean_sql(column_name):
    column = quote_identifier(column_name)
    return (
        f"REPLACE(REPLACE(REPLACE(REPLACE(REPLACE({column}, ' ', ''), '-', ''), '+', ''), '.', ''), '(', '')"
    )


def dedupe_by_id(rows):
    seen = set()
    result = []
    for row in rows or []:
        row_id = row.get("id")
        key = row_id if row_id is not None else json.dumps(row, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def attach_patient_names(rows):
    if not rows:
        return rows
    variants_by_mobile = {row["mobile"]: phone_variants(row["mobile"]) for row in rows}
    all_variants = sorted({variant for variants in variants_by_mobile.values() for variant in variants})
    if not all_variants:
        return rows
    placeholders = ", ".join(["%s"] * len(all_variants))
    clean_contact = "REPLACE(REPLACE(REPLACE(REPLACE(contact_mobile, ' ', ''), '-', ''), '+', ''), '.', '')"
    clean_alternate = "REPLACE(REPLACE(REPLACE(REPLACE(alternate_mobile, ' ', ''), '-', ''), '+', ''), '.', '')"
    sql = f"""
        SELECT id, patient_code, full_name, contact_mobile, alternate_mobile
        FROM hpatient_master
        WHERE {clean_contact} IN ({placeholders})
           OR {clean_alternate} IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        LIMIT 500
    """
    try:
        with lead_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, all_variants + all_variants)
                patients = cursor.fetchall()
    except Exception as exc:
        log_line("incoming-webhook.log", "patient_name_lookup_failed", error=str(exc))
        return rows

    contact_matches = {}
    alternate_matches = {}
    for patient in patients:
        for variant in phone_variants(patient.get("contact_mobile")):
            contact_matches.setdefault(variant, patient)
        for variant in phone_variants(patient.get("alternate_mobile")):
            alternate_matches.setdefault(variant, patient)

    for row in rows:
        matched = None
        for variant in variants_by_mobile.get(row["mobile"], set()):
            matched = contact_matches.get(variant)
            if matched:
                break
        if not matched:
            for variant in variants_by_mobile.get(row["mobile"], set()):
                matched = alternate_matches.get(variant)
                if matched:
                    break
        if matched:
            row["patient_name"] = matched.get("full_name") or ""
            row["patient_code"] = matched.get("patient_code") or ""
        else:
            row["patient_name"] = ""
            row["patient_code"] = ""
    return rows


def resolve_caller(cursor, variants):
    if not variants:
        return None
    params = list(variants)
    placeholders = ", ".join(["%s"] * len(params))
    cursor.execute(
        f"""
        SELECT c.id, c.caller_code, c.full_name, c.primary_mobile, c.alternate_mobile,
               c.email, c.caller_status, c.active, c.created_at, c.updated_at
        FROM hcaller_mobile_map mm
        INNER JOIN hcaller_master c ON c.id = mm.caller_id
        WHERE mm.is_active = 1 AND mm.mobile_norm IN ({placeholders})
        ORDER BY mm.id DESC
        LIMIT 1
        """,
        params,
    )
    caller = cursor.fetchone()
    if caller:
        return caller

    primary_clean = mobile_clean_sql("primary_mobile")
    alternate_clean = mobile_clean_sql("alternate_mobile")
    cursor.execute(
        f"""
        SELECT id, caller_code, full_name, primary_mobile, alternate_mobile,
               email, caller_status, active, created_at, updated_at
        FROM hcaller_master
        WHERE {primary_clean} IN ({placeholders})
           OR {alternate_clean} IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        params + params,
    )
    return cursor.fetchone()


def fetch_linked_patients(cursor, caller_id):
    if not caller_id:
        return []
    cursor.execute(
        """
        SELECT p.id, p.patient_code, p.title, p.full_name, p.labmate_pid, p.panel_company,
               p.card_number, p.tag, p.gender, p.date_of_birth, p.age_years,
               p.contact_mobile, p.alternate_mobile, p.patient_status,
               l.is_active AS link_is_active, l.created_at AS linked_at
        FROM hcaller_patient_link l
        INNER JOIN hpatient_master p ON p.id = l.patient_id
        WHERE l.caller_id = %s AND l.is_active = 1
        ORDER BY l.created_at DESC, p.full_name ASC
        """,
        (caller_id,),
    )
    return dedupe_by_id(cursor.fetchall())


def fetch_patient_addresses(cursor, patient_ids):
    patient_ids = [item for item in patient_ids if item]
    if not patient_ids:
        return []
    placeholders = ", ".join(["%s"] * len(patient_ids))
    cursor.execute(
        f"""
        SELECT pal.patient_id, pal.address_id, pal.is_default, pal.is_active,
               a.address_type, a.house_flat_no, a.floor, a.block_tower_no,
               a.street_line, a.landmark, a.city, a.colony_id, a.colony_name,
               a.pincode, a.route_no, a.google_location, a.access_notes,
               a.created_at
        FROM hpatient_address_link pal
        INNER JOIN haddress_master a ON a.id = pal.address_id
        WHERE pal.patient_id IN ({placeholders}) AND pal.is_active = 1
        ORDER BY pal.is_default DESC, a.created_at DESC
        """,
        patient_ids,
    )
    return cursor.fetchall()


def fetch_reference_addresses(cursor, caller_id):
    if not caller_id:
        return []
    cursor.execute(
        """
        SELECT id, caller_id, area, city, pincode, routename, address,
               status, created_at, updated_at
        FROM hcaller_reference_address
        WHERE caller_id = %s AND (status IS NULL OR status != 'removed')
        ORDER BY updated_at DESC, created_at DESC
        """,
        (caller_id,),
    )
    return dedupe_by_id(cursor.fetchall())


def fetch_home_collection_bookings(cursor, caller_id):
    if not caller_id:
        return []
    cursor.execute(
        """
        SELECT id, booking_code, caller_id, selected_address_id,
               preferred_visit_date, preferred_time_slot, booking_status,
               assigned_phlebotomist_id, created_at, created_by,
               lead_id, remarks, booking_tags, paying_amount, credit_amount,
               total_amount
        FROM hhome_collection_booking
        WHERE caller_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (caller_id,),
    )
    bookings = dedupe_by_id(cursor.fetchall())
    booking_ids = [row["id"] for row in bookings if row.get("id")]
    if not booking_ids:
        return bookings

    placeholders = ", ".join(["%s"] * len(booking_ids))
    cursor.execute(
        f"""
        SELECT bp.id, bp.booking_id, bp.patient_id, bp.booking_patient_status,
               bp.patient_final_amount, bp.payment_mode, bp.payment_amount,
               bp.due_amount, bp.cancel_reason, bp.cancel_remark,
               bp.reschedule_requested, bp.reschedule_date, bp.reschedule_slot,
               bp.created_at,
               p.patient_code, p.full_name, p.contact_mobile, p.alternate_mobile
        FROM hhome_collection_booking_patient bp
        LEFT JOIN hpatient_master p ON p.id = bp.patient_id
        WHERE bp.booking_id IN ({placeholders})
        ORDER BY bp.booking_id DESC, bp.id ASC
        """,
        booking_ids,
    )
    patients_by_booking = {}
    for row in cursor.fetchall():
        patients_by_booking.setdefault(row["booking_id"], []).append(row)
    for booking in bookings:
        booking["patients"] = patients_by_booking.get(booking["id"], [])
    return bookings


def fetch_leads_by_mobile(cursor, variants):
    if not variants:
        return []
    params = list(variants)
    placeholders = ", ".join(["%s"] * len(params))
    phone_clean = mobile_clean_sql("phone")
    alt_clean = mobile_clean_sql("alt_phone")
    cursor.execute(
        f"""
        SELECT id, lead_id, name, phone, alt_phone, status, tags, remarks,
               visit_window, created_by, created_at
        FROM leads
        WHERE ({phone_clean} IN ({placeholders}) OR {alt_clean} IN ({placeholders}))
          AND COALESCE({phone_clean}, '') != ''
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        params + params,
    )
    return dedupe_by_id(cursor.fetchall())


def fetch_tickets_by_mobile(cursor, variants):
    if not variants:
        return []
    params = list(variants)
    placeholders = ", ".join(["%s"] * len(params))
    mobile_clean = mobile_clean_sql("mobile_number")
    cursor.execute(
        f"""
        SELECT id, ticket_origin, ticket_category, patient_name, client_name,
               mobile_number, status, assign_to_user_id, created_by,
               created_at, commitment_at
        FROM tickets
        WHERE {mobile_clean} IN ({placeholders})
          AND COALESCE({mobile_clean}, '') != ''
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        params,
    )
    return dedupe_by_id(cursor.fetchall())


def unified_mobile_lookup(mobile):
    variants = phone_variants(mobile)
    normalized_mobile = next((item for item in sorted(variants, key=len) if len(item) == 10), phone_digits(mobile))
    response = {
        "ok": True,
        "search_mobile": str(mobile or ""),
        "normalized_mobile": normalized_mobile,
        "mobile_variants": sorted(variants),
        "caller": None,
        "linked_patients": [],
        "addresses": [],
        "reference_addresses": [],
        "home_collection_bookings": [],
        "leads": [],
        "tickets": [],
    }
    if not variants:
        return response

    with lead_db_connection() as conn:
        with conn.cursor() as cursor:
            caller = resolve_caller(cursor, variants)
            response["caller"] = caller
            if caller:
                response["linked_patients"] = fetch_linked_patients(cursor, caller["id"])
                patient_ids = [row["id"] for row in response["linked_patients"]]
                response["addresses"] = fetch_patient_addresses(cursor, patient_ids)
                response["reference_addresses"] = fetch_reference_addresses(cursor, caller["id"])
                response["home_collection_bookings"] = fetch_home_collection_bookings(cursor, caller["id"])
            response["leads"] = fetch_leads_by_mobile(cursor, variants)
            response["tickets"] = fetch_tickets_by_mobile(cursor, variants)
    return response


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return {
        "id": user_id,
        "username": session.get("username", ""),
        "display_name": session.get("display_name", ""),
        "role": session.get("role", "agent"),
    }


def require_user():
    user = current_user()
    if not user:
        return None, (jsonify(ok=False, error="Login required"), 401)
    return user, None


def ensure_conversation_state(cursor, mobile):
    cursor.execute(
        """
        INSERT INTO conversation_state (mobile, status)
        VALUES (%s, 'open')
        ON DUPLICATE KEY UPDATE mobile = VALUES(mobile)
        """,
        (mobile,),
    )
    cursor.execute("SELECT * FROM conversation_state WHERE mobile = %s", (mobile,))
    return cursor.fetchone()


def log_conversation_action(
    cursor,
    mobile,
    action_type,
    user,
    old_state=None,
    new_owner=None,
    old_value=None,
    new_value=None,
    reason="",
    payload=None,
):
    old_state = old_state or {}
    new_owner = new_owner or {}
    cursor.execute(
        """
        INSERT INTO conversation_actions
          (mobile, action_type, performed_by_user_id, performed_by_name,
           old_owner_user_id, old_owner_name, new_owner_user_id, new_owner_name,
           old_value, new_value, reason, payload_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            mobile,
            action_type,
            user["id"],
            user["display_name"],
            old_state.get("owner_user_id"),
            old_state.get("owner_name"),
            new_owner.get("id"),
            new_owner.get("display_name"),
            old_value,
            new_value,
            reason,
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )


def ensure_current_owner(state_row, user):
    if state_row.get("status") == "closed":
        return "Conversation is closed"
    if state_row.get("owner_user_id") != user["id"]:
        owner = state_row.get("owner_name") or "another user"
        return f"Only current owner can perform this action. Current owner: {owner}"
    return ""


def download_netcore_media(media_id, kind, mime_type="", mobile=""):
    if not media_id or not CONFIG["netcore_token"]:
        return ""
    extension = mimetypes.guess_extension(mime_type or "") or (".pdf" if kind == "document" else ".jpg")
    if extension == ".jpe":
        extension = ".jpg"
    folder = UPLOAD_DIR / "incoming"
    folder.mkdir(parents=True, exist_ok=True)
    mobile_prefix = normalize_mobile(mobile) or "unknown"
    saved_name = f"{mobile_prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}{extension}"
    target = folder / saved_name
    response = requests.get(
        f"{CONFIG['netcore_media_url'].rstrip('/')}/{media_id}",
        headers={"Authorization": f"Bearer {CONFIG['netcore_token']}"},
        timeout=30,
    )
    response.raise_for_status()
    target.write_bytes(response.content)
    return public_url(f"uploads/incoming/{saved_name}")


def normalize_incoming_payload(data):
    item = data.get("incoming_message", data)
    if isinstance(item, list):
        item = item[0] if item else {}
    if not isinstance(item, dict):
        raise ValueError("incoming_message array missing")

    mobile = str(item.get("from") or item.get("mobile") or item.get("phone") or "").strip()
    if not mobile:
        raise ValueError("incoming mobile/from missing")

    received_at = item.get("received_at") or item.get("timestamp") or int(datetime.now().timestamp())
    received_dt = parse_payload_date(received_at)
    text_type = item.get("text_type") if isinstance(item.get("text_type"), dict) else {}
    image_type = item.get("image_type") if isinstance(item.get("image_type"), dict) else {}
    video_type = item.get("video_type") if isinstance(item.get("video_type"), dict) else {}
    document_type = item.get("document_type") if isinstance(item.get("document_type"), dict) else {}

    image_id = str(image_type.get("id") or image_type.get("media_id") or "").strip()
    image_url = str(image_type.get("url") or image_type.get("link") or image_type.get("media_url") or item.get("image_url") or "").strip()
    document_id = str(document_type.get("id") or document_type.get("media_id") or "").strip()
    document_url = str(document_type.get("url") or document_type.get("link") or document_type.get("media_url") or item.get("document_url") or "").strip()
    document_name = str(document_type.get("filename") or document_type.get("name") or Path(document_url).name or "").strip()

    if image_id and not image_url:
        try:
            image_url = download_netcore_media(image_id, "image", str(image_type.get("mime_type") or "image/jpeg"), mobile)
        except Exception as exc:
            log_line("incoming-webhook.log", "incoming_image_download_failed", mediaId=image_id, error=str(exc))
    if document_id and not document_url:
        try:
            document_url = download_netcore_media(document_id, "document", str(document_type.get("mime_type") or "application/pdf"), mobile)
        except Exception as exc:
            log_line("incoming-webhook.log", "incoming_document_download_failed", mediaId=document_id, error=str(exc))

    return {
        "mobile": mobile,
        "msg": str(text_type.get("text") or item.get("text") or item.get("msg") or image_type.get("caption") or document_type.get("caption") or ""),
        "img": image_url or str(image_type.get("sha256") or ""),
        "vedio": str(video_type.get("sha256") or ""),
        "pdff": document_name or (Path(document_url).name if document_url else ""),
        "docid": document_url or document_id,
        "imgid": image_url or image_id,
        "wabadatetime": display_date(received_dt),
        "received_at": str(received_at),
    }


def normalize_delivery_payload(data):
    item = data.get("delivery_status", data)
    if isinstance(item, list):
        item = item[0] if item else {}
    if not isinstance(item, dict):
        raise ValueError("delivery_status array missing")

    nested = item.get("data") if isinstance(item.get("data"), dict) else {}
    provider_message_id = str(
        item.get("ncmessage_id") or item.get("message_id") or item.get("id") or nested.get("id") or ""
    ).strip()
    if not provider_message_id:
        raise ValueError("provider message id missing")

    return {
        "provider_message_id": provider_message_id,
        "status": str(item.get("status") or item.get("delivery_status") or "").strip(),
        "status_remark": str(item.get("status_remark") or item.get("remark") or item.get("reason") or "").strip(),
        "received_at": str(item.get("received_at") or item.get("timestamp") or item.get("created_at") or datetime.now().isoformat()).strip(),
    }


def netcore_message_payload(mobile, msg, media):
    base = {
        "recipient_whatsapp": mobile,
        "recipient_type": "individual",
        "source": CONFIG["netcore_source"],
        "x-apiheader": "custom_data",
    }
    if media and media["kind"] == "image":
        return {
            **base,
            "message_type": "media_template",
            "type_media_template": {"type": "image", "url": media["url"]},
            "type_template": [{
                "name": CONFIG["netcore_image_template"],
                "attributes": [msg or "Raj"],
                "language": {"locale": "en", "policy": "deterministic"},
            }],
        }
    if media and media["kind"] == "document":
        payload = {
            **base,
            "message_type": "document",
            "type_document": [{"link": media["url"], "filename": media["filename"] or "document.pdf"}],
        }
        if msg:
            payload["type_document"][0]["caption"] = msg
        return payload
    return {
        **base,
        "message_type": "text",
        "type_text": [{"preview_url": "false", "content": msg}],
    }


def send_via_provider(mobile, msg, media=None):
    provider = CONFIG["whatsapp_provider"]
    log_line(
        "outgoing-whatsapp.log",
        "send_attempt",
        provider=provider,
        mobile=mask_mobile(mobile),
        messageLength=len(msg),
        mediaKind=(media or {}).get("kind", ""),
    )

    if provider == "disabled":
        result = {"skipped": True, "provider": "disabled"}
        log_line("outgoing-whatsapp.log", "send_skipped", **result)
        return result

    if provider == "netcore":
        if not CONFIG["netcore_token"] or not CONFIG["netcore_source"]:
            raise ValueError("NETCORE_TOKEN and NETCORE_SOURCE are required")
        url = CONFIG["netcore_image_url"] if media and media["kind"] == "image" else CONFIG["netcore_url"]
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {CONFIG['netcore_token']}", "Content-Type": "application/json"},
            json={"message": [netcore_message_payload(mobile, msg, media)]},
            timeout=30,
        )
        text = response.text
        log_line("outgoing-whatsapp.log", "netcore_response", status=response.status_code, ok=response.ok, body=text[:2000])
        response.raise_for_status()
        try:
            provider_message_id = response.json().get("data", {}).get("id") or ""
        except ValueError:
            provider_message_id = ""
        return {"provider": "netcore", "providerMessageId": provider_message_id, "response": text}

    if provider == "stewindia":
        if not CONFIG["stewindia_token"]:
            raise ValueError("STEWINDIA_TOKEN is required")
        response = requests.get(
            CONFIG["stewindia_url"],
            params={"token": CONFIG["stewindia_token"], "phone": mobile, "message": msg},
            timeout=30,
        )
        text = response.text
        log_line("outgoing-whatsapp.log", "stewindia_response", status=response.status_code, ok=response.ok, body=text[:2000])
        response.raise_for_status()
        return {"provider": "stewindia", "providerMessageId": "", "response": text}

    raise ValueError(f"Unknown WHATSAPP_PROVIDER: {provider}")


@app.get("/login")
def login_page():
    if current_user():
        return redirect(url_for("index"))
    return render_template("login.html")


@app.post("/login")
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, display_name, password_hash, role FROM users WHERE username = %s AND is_active = 1",
                (username,),
            )
            user = cursor.fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid username or password"), 401
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["display_name"] = user["display_name"]
    session["role"] = user["role"]
    return redirect(url_for("index"))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.get("/")
def index():
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    return render_template(
        "index.html",
        provider=CONFIG["whatsapp_provider"],
        database=CONFIG["database"],
        table=CONFIG["table"],
        current_user=user,
    )


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.post("/api/uploads")
def upload_file():
    user, error = require_user()
    if error:
        return error
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(ok=False, error="File missing"), 400
    original_name = secure_filename(file.filename)
    kind = upload_kind(original_name)
    if not kind:
        return jsonify(ok=False, error="Only JPG, PNG, WEBP, and PDF files are allowed"), 400
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex}_{original_name}"
    file.save(UPLOAD_DIR / saved_name)
    url_path = f"uploads/{saved_name}"
    return jsonify(ok=True, media={"kind": kind, "filename": original_name, "url": public_url(url_path), "path": f"/{url_path}"})


@app.get("/api/stats")
def stats():
    user, error = require_user()
    if error:
        return error
    table = quote_identifier(CONFIG["table"])
    today_start, tomorrow_start = today_bounds()
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {table} WHERE datetimess >= %s AND datetimess < %s",
                (today_start, tomorrow_start),
            )
            today = cursor.fetchone()["total"]
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE color = 'red'")
            incoming = cursor.fetchone()["total"]
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE color = 'green'")
            outgoing = cursor.fetchone()["total"]
    return jsonify(ok=True, total=total, today=today, incoming=incoming, outgoing=outgoing, provider=CONFIG["whatsapp_provider"])


@app.get("/api/conversations")
def conversations():
    user, error = require_user()
    if error:
        return error
    date = request.args.get("date", "").strip() or datetime.now().strftime("%Y-%m-%d")
    query = request.args.get("q", "").strip()
    queue = request.args.get("queue", "All Chats").strip()
    start_date, end_date = day_bounds(date)
    params = [start_date, end_date]
    filters = ["(msg != '' OR img != '' OR pdff != '' OR docid != '' OR imgid != '')", "datetimess >= %s", "datetimess < %s"]

    if query:
        filters.append("(mobile LIKE %s OR msg LIKE %s OR empname LIKE %s)")
        params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])
    if queue == "Incoming":
        filters.append("color = 'red'")
    elif queue == "Outgoing":
        filters.append("color = 'green'")

    where_sql = f"WHERE {' AND '.join(filters)}"
    table = quote_identifier(CONFIG["table"])
    sql = f"""
        SELECT w.id, w.mobile, w.msg, w.img, w.vedio, w.pdff, w.docid, w.imgid,
               w.wabadatetime, w.empname, w.datetimess, w.color, w.status,
               w.provider_message_id, w.delivery_status,
               cs.owner_user_id, cs.owner_name, cs.conversation_type,
               cs.status AS workflow_status, cs.closed_at, cs.closure_note,
               cs.updated_at AS workflow_updated_at
        FROM {table} w
        INNER JOIN (
          SELECT mobile, MAX(id) AS max_id
          FROM {table}
          {where_sql}
          GROUP BY mobile
        ) latest ON latest.max_id = w.id
        LEFT JOIN conversation_state cs ON cs.mobile = w.mobile
        ORDER BY w.datetimess DESC
        LIMIT 300
    """
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    rows = attach_patient_names(rows)
    return jsonify(ok=True, rows=rows)


@app.get("/api/conversations/<mobile>/messages")
def list_messages(mobile):
    user, error = require_user()
    if error:
        return error
    normalized = normalize_mobile(mobile)
    if not normalized:
        return jsonify(ok=False, error="Mobile missing"), 400
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, mobile, msg, img, vedio, pdff, docid, imgid, wabadatetime, empname,
                       datetimess, color, status, provider_message_id, delivery_status,
                       delivery_status_remark, delivery_received_at
                FROM {quote_identifier(CONFIG['table'])}
                WHERE mobile = %s
                ORDER BY id ASC
                LIMIT 1000
                """,
                (normalized,),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT note, created_by_name, created_at
                FROM conversation_notes
                WHERE mobile = %s
                ORDER BY created_at ASC
                LIMIT 300
                """,
                (normalized,),
            )
            notes = cursor.fetchall()
    rows = attach_patient_names(rows)
    for note in notes:
        rows.append({
            "note": note["note"],
            "time": str(note["created_at"]),
            "empname": note["created_by_name"],
            "datetimess": note["created_at"],
        })
    return jsonify(ok=True, mobile=normalized, rows=rows)


@app.get("/api/users")
def list_users():
    user, error = require_user()
    if error:
        return error
    query = request.args.get("q", "").strip()
    params = []
    filters = ["is_active = 1"]
    if query:
        filters.append("(display_name LIKE %s OR username LIKE %s)")
        params.extend([f"%{query}%", f"%{query}%"])
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, username, display_name, role
                FROM users
                WHERE {' AND '.join(filters)}
                ORDER BY display_name ASC
                LIMIT 25
                """,
                params,
            )
            rows = cursor.fetchall()
    return jsonify(ok=True, users=rows, currentUser=user)


@app.get("/api/mobile-lookup")
def mobile_lookup():
    user, error = require_user()
    if error:
        return error
    mobile = request.args.get("mobile", "").strip()
    if not mobile:
        return jsonify(ok=False, error="Mobile number missing"), 400
    try:
        return jsonify(unified_mobile_lookup(mobile))
    except Exception as exc:
        log_line("incoming-webhook.log", "unified_mobile_lookup_failed", mobile=mask_mobile(mobile), error=str(exc))
        return jsonify(ok=False, error=str(exc)), 500


@app.post("/api/conversations/<mobile>/ownership")
def take_ownership(mobile):
    user, error = require_user()
    if error:
        return error
    normalized = normalize_mobile(mobile)
    if not normalized:
        return jsonify(ok=False, error="Mobile missing"), 400
    with db_connection() as conn:
        with conn.cursor() as cursor:
            old_state = ensure_conversation_state(cursor, normalized)
            if old_state.get("status") == "closed":
                return jsonify(ok=False, error="Conversation is closed"), 400
            if old_state.get("owner_user_id") and old_state.get("owner_user_id") != user["id"]:
                return jsonify(ok=False, error=f"Already owned by {old_state.get('owner_name') or 'another user'}"), 409
            cursor.execute(
                """
                UPDATE conversation_state
                SET owner_user_id = %s, owner_name = %s, status = 'owned'
                WHERE mobile = %s
                """,
                (user["id"], user["display_name"], normalized),
            )
            log_conversation_action(
                cursor,
                normalized,
                "take_ownership",
                user,
                old_state=old_state,
                new_owner=user,
                new_value=user["display_name"],
            )
            cursor.execute("SELECT * FROM conversation_state WHERE mobile = %s", (normalized,))
            state_row = cursor.fetchone()
    return jsonify(ok=True, state=state_row)


@app.post("/api/conversations/<mobile>/type")
def update_conversation_type(mobile):
    user, error = require_user()
    if error:
        return error
    normalized = normalize_mobile(mobile)
    data = request.get_json(silent=True) or {}
    conversation_type = str(data.get("conversation_type") or data.get("type") or "").strip()[:80]
    if not normalized or not conversation_type:
        return jsonify(ok=False, error="Conversation type missing"), 400
    with db_connection() as conn:
        with conn.cursor() as cursor:
            old_state = ensure_conversation_state(cursor, normalized)
            owner_error = ensure_current_owner(old_state, user)
            if owner_error:
                return jsonify(ok=False, error=owner_error), 403
            cursor.execute(
                "UPDATE conversation_state SET conversation_type = %s WHERE mobile = %s",
                (conversation_type, normalized),
            )
            log_conversation_action(
                cursor,
                normalized,
                "update_type",
                user,
                old_state=old_state,
                old_value=old_state.get("conversation_type"),
                new_value=conversation_type,
            )
            cursor.execute("SELECT * FROM conversation_state WHERE mobile = %s", (normalized,))
            state_row = cursor.fetchone()
    return jsonify(ok=True, state=state_row)


@app.post("/api/conversations/<mobile>/close")
def close_conversation(mobile):
    user, error = require_user()
    if error:
        return error
    normalized = normalize_mobile(mobile)
    data = request.get_json(silent=True) or {}
    conversation_type = str(data.get("conversation_type") or data.get("type") or "").strip()[:80]
    note = str(data.get("note") or data.get("closure_note") or "").strip()
    if not normalized or not conversation_type:
        return jsonify(ok=False, error="Conversation type missing"), 400
    with db_connection() as conn:
        with conn.cursor() as cursor:
            old_state = ensure_conversation_state(cursor, normalized)
            owner_error = ensure_current_owner(old_state, user)
            if owner_error:
                return jsonify(ok=False, error=owner_error), 403
            cursor.execute(
                """
                UPDATE conversation_state
                SET conversation_type = %s, status = 'closed',
                    closed_by_user_id = %s, closed_by_name = %s,
                    closed_at = NOW(), closure_note = %s
                WHERE mobile = %s
                """,
                (conversation_type, user["id"], user["display_name"], note, normalized),
            )
            log_conversation_action(
                cursor,
                normalized,
                "close_conversation",
                user,
                old_state=old_state,
                old_value=old_state.get("status"),
                new_value="closed",
                reason=note,
                payload={"conversation_type": conversation_type},
            )
            cursor.execute("SELECT * FROM conversation_state WHERE mobile = %s", (normalized,))
            state_row = cursor.fetchone()
    return jsonify(ok=True, state=state_row)


@app.post("/api/conversations/<mobile>/notes")
def add_note(mobile):
    user, error = require_user()
    if error:
        return error
    normalized = normalize_mobile(mobile)
    data = request.get_json(silent=True) or {}
    note = str(data.get("note") or "").strip()
    if not normalized or not note:
        return jsonify(ok=False, error="Note missing"), 400
    with db_connection() as conn:
        with conn.cursor() as cursor:
            old_state = ensure_conversation_state(cursor, normalized)
            owner_error = ensure_current_owner(old_state, user)
            if owner_error:
                return jsonify(ok=False, error=owner_error), 403
            cursor.execute(
                """
                INSERT INTO conversation_notes (mobile, note, created_by_user_id, created_by_name)
                VALUES (%s, %s, %s, %s)
                """,
                (normalized, note, user["id"], user["display_name"]),
            )
            note_id = cursor.lastrowid
            log_conversation_action(
                cursor,
                normalized,
                "add_note",
                user,
                old_state=old_state,
                new_value=note,
            )
    return jsonify(ok=True, id=note_id)


@app.post("/api/conversations/<mobile>/reassign")
def reassign_conversation(mobile):
    user, error = require_user()
    if error:
        return error
    normalized = normalize_mobile(mobile)
    data = request.get_json(silent=True) or {}
    new_owner_id = data.get("owner_user_id")
    reason = str(data.get("reason") or "").strip()
    if not normalized or not new_owner_id:
        return jsonify(ok=False, error="New owner missing"), 400
    with db_connection() as conn:
        with conn.cursor() as cursor:
            old_state = ensure_conversation_state(cursor, normalized)
            owner_error = ensure_current_owner(old_state, user)
            if owner_error:
                return jsonify(ok=False, error=owner_error), 403
            cursor.execute(
                "SELECT id, display_name FROM users WHERE id = %s AND is_active = 1",
                (new_owner_id,),
            )
            new_owner = cursor.fetchone()
            if not new_owner:
                return jsonify(ok=False, error="Owner not found"), 404
            cursor.execute(
                """
                UPDATE conversation_state
                SET owner_user_id = %s, owner_name = %s, status = 'owned'
                WHERE mobile = %s
                """,
                (new_owner["id"], new_owner["display_name"], normalized),
            )
            log_conversation_action(
                cursor,
                normalized,
                "reassign",
                user,
                old_state=old_state,
                new_owner=new_owner,
                old_value=old_state.get("owner_name"),
                new_value=new_owner["display_name"],
                reason=reason,
            )
            cursor.execute("SELECT * FROM conversation_state WHERE mobile = %s", (normalized,))
            state_row = cursor.fetchone()
    return jsonify(ok=True, state=state_row)


@app.post("/api/conversations/<mobile>/messages")
def create_message(mobile):
    user, error = require_user()
    if error:
        return error
    normalized = normalize_mobile(mobile)
    data = request.get_json(silent=True) or {}
    msg = str(data.get("msg") or data.get("message") or "").strip()
    empname = user["display_name"][:225]
    media = normalize_media(data)
    if not normalized:
        return jsonify(ok=False, error="Mobile missing"), 400
    if not msg and not media["url"]:
        return jsonify(ok=False, error="Message or attachment missing"), 400
    if media["url"] and not media["kind"]:
        return jsonify(ok=False, error="Unsupported attachment type"), 400

    with db_connection() as conn:
        with conn.cursor() as cursor:
            state_row = ensure_conversation_state(cursor, normalized)
    owner_error = ensure_current_owner(state_row, user)
    if owner_error:
        return jsonify(ok=False, error=owner_error), 403

    try:
        provider_result = send_via_provider(normalized, msg, media if media["url"] else None)
        provider_message_id = provider_result.get("providerMessageId") or None
        delivery_status = "accepted" if provider_message_id else None
        image_value = media["url"] if media["kind"] == "image" else ""
        image_id = media["url"] if media["kind"] == "image" else ""
        pdf_name = media["filename"] if media["kind"] == "document" else ""
        document_id = media["url"] if media["kind"] == "document" else ""
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {quote_identifier(CONFIG['table'])}
                      (mobile, msg, img, vedio, pdff, docid, imgid, wabadatetime, empname,
                       color, empnamestatus, datetimesnot, provider_message_id, delivery_status)
                    VALUES (%s, %s, %s, '', %s, %s, %s, %s, %s, 'green', '', '', %s, %s)
                    """,
                    (normalized, msg, image_value, pdf_name, document_id, image_id, display_date(), empname, provider_message_id, delivery_status),
                )
                row_id = cursor.lastrowid
        log_line("outgoing-whatsapp.log", "message_saved", id=row_id, mobile=mask_mobile(normalized), provider=provider_result.get("provider"), providerMessageId=provider_message_id or "")
        return jsonify(ok=True, id=row_id, provider=provider_result), 201
    except Exception as exc:
        log_line("outgoing-whatsapp.log", "send_failed", mobile=mask_mobile(normalized), error=str(exc))
        return jsonify(ok=False, error=str(exc)), 500


@app.post("/webhook/incoming-message")
def incoming_webhook():
    raw_body = request.get_data(as_text=True)
    data = request.get_json(silent=True) or {}
    try:
        payload = normalize_incoming_payload(data)
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {quote_identifier(CONFIG['table'])}
                      (mobile, msg, img, vedio, pdff, docid, imgid, wabadatetime, empname,
                       color, empnamestatus, datetimesnot)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Patient', 'red', '', '')
                    """,
                    (payload["mobile"], payload["msg"], payload["img"], payload["vedio"], payload["pdff"], payload["docid"], payload["imgid"], payload["wabadatetime"]),
                )
                cursor.execute(
                    "INSERT INTO incoming_webhook_logs (mobile, received_at, payload_json) VALUES (%s, %s, %s)",
                    (payload["mobile"], payload["received_at"], raw_body),
                )
        log_line("incoming-webhook.log", "incoming_message_saved", mobile=mask_mobile(payload["mobile"]), receivedAt=payload["received_at"])
        return jsonify(ok=True, message="Incoming WhatsApp message saved", data=payload)
    except Exception as exc:
        log_line("incoming-webhook.log", "incoming_message_failed", error=str(exc), body=raw_body[:2000])
        return jsonify(ok=False, error=str(exc)), 500


@app.post("/webhook/delivery-status")
def delivery_webhook():
    raw_body = request.get_data(as_text=True)
    data = request.get_json(silent=True) or {}
    try:
        payload = normalize_delivery_payload(data)
        current_updated = 0
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {quote_identifier(CONFIG['table'])}
                    SET delivery_status = %s, delivery_status_remark = %s, delivery_received_at = %s
                    WHERE provider_message_id = %s
                    """,
                    (payload["status"], payload["status_remark"], payload["received_at"], payload["provider_message_id"]),
                )
                current_updated = cursor.rowcount
                cursor.execute(
                    """
                    INSERT INTO delivery_webhook_logs
                      (provider_message_id, status, status_remark, received_at, payload_json)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (payload["provider_message_id"], payload["status"], payload["status_remark"], payload["received_at"], raw_body),
                )

        safe_name = str(payload["received_at"] or datetime.now().isoformat()).replace("/", "_").replace("\\", "_").replace(":", "_")[:120]
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with (LOG_DIR / f"{safe_name}.txt").open("a", encoding="utf-8") as handle:
                handle.write(raw_body + "\n")
        except Exception as file_error:
            log_line("delivery-status.log", "delivery_payload_file_write_failed", error=str(file_error), **payload)
        log_line("delivery-status.log", "delivery_status_received", currentUpdated=current_updated, **payload)
        return jsonify(ok=True, message="Delivery status saved", data={**payload, "currentUpdated": current_updated})
    except Exception as exc:
        log_line("delivery-status.log", "delivery_status_failed", error=str(exc), body=raw_body[:2000])
        return jsonify(ok=False, error=str(exc)), 500


if __name__ == "__main__":
    init_db()
    ssl_context = None
    if CONFIG["ssl_cert_file"] and CONFIG["ssl_key_file"]:
        cert_path = Path(CONFIG["ssl_cert_file"])
        key_path = Path(CONFIG["ssl_key_file"])
        if not cert_path.is_absolute():
            cert_path = ROOT / cert_path
        if not key_path.is_absolute():
            key_path = ROOT / key_path
        if not cert_path.exists():
            raise FileNotFoundError(f"SSL cert not found: {cert_path}")
        if not key_path.exists():
            raise FileNotFoundError(f"SSL key not found: {key_path}")
        ssl_context = (str(cert_path), str(key_path))

    scheme = "https" if ssl_context else "http"
    print(f"Patient WhatsApp Hub: {scheme}://{CONFIG['server_host']}:{CONFIG['server_port']}")
    print(f"Incoming webhook:     {scheme}://{CONFIG['server_host']}:{CONFIG['server_port']}/webhook/incoming-message")
    print(f"Delivery webhook:     {scheme}://{CONFIG['server_host']}:{CONFIG['server_port']}/webhook/delivery-status")
    print(f"Database table:       {CONFIG['database']}.{CONFIG['table']}")
    print(f"WhatsApp provider:    {CONFIG['whatsapp_provider']}")
    app.run(host=CONFIG["server_host"], port=CONFIG["server_port"], debug=False, ssl_context=ssl_context)
