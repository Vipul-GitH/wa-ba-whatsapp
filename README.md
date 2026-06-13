# ARPRA WhatsApp Console

Python/Jinja/CSS WhatsApp communication hub connected to the real WhatsApp webhook backend.

## Run

```powershell
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:9010
```

Incoming webhook:

```text
http://127.0.0.1:9010/webhook/incoming-message
```

Delivery status webhook:

```text
http://127.0.0.1:9010/webhook/delivery-status
```
