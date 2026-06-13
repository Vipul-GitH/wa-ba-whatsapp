# ARPRA WhatsApp Official API Communication Hub

## Updated UI Structure

The module is a Communication Hub above ARPRA workflows, not a generic inbox.

- Left sidebar: All Chats, Unassigned, My Chats, Team Chats, Waiting For Patient, SLA Breached, Archived.
- Chat list: patient/contact name, last message, last time, unread count, owner, SLA indicator, tags.
- Center panel: WhatsApp conversation, ownership lock, SLA status, text/PDF/audio/internal-note messages, reply composer with local Hinglish/lab dictionary, professional CCE emoji picker, and work-file attachment picker.
- Conversation type: CCE can mark or change type per conversation at any time, then explicitly saves that type so the tag has an auditable source. The same mobile/patient may have one conversation typed Booking/Home Collection and a later conversation typed Report Query. Closure still requires a final type.
- Right workspace: linked contact, linked patients, tickets, leads, home collections, previous conversations, notes, tags, audit summary.
- Side drawers: Link, Create, Add Note, Add Tag, Reassign. The Link drawer asks whether the agent wants to link a Patient, Ticket, or Lead. The Create drawer asks whether the agent wants to create a Ticket, Lead, or Home Collection.

## Component Hierarchy

- `CommunicationHubApp`
- `TopBand`
- `DashboardStats`
- `QueueSidebar`
- `ConversationList`
- `ConversationPanel`
- `OwnershipBar`
- `MessageThread`
- `ContextWorkspace`
- `ContextBlock`
- `QuickActions`
- `SideDrawerWorkflow`

## Database Schema Proposal

```sql
chat_conversations (
  id bigint primary key,
  wa_chat_id varchar(80) unique not null,
  mobile varchar(20) not null,
  display_name varchar(160),
  status varchar(40),
  owner_user_id bigint null,
  owner_taken_at datetime null,
  last_message_at datetime,
  last_reply_at datetime,
  archived_at datetime null,
  created_at datetime,
  updated_at datetime
);

chat_messages (
  id bigint primary key,
  conversation_id bigint not null,
  direction enum('inbound','outbound','internal_note') not null,
  message_type enum('text','image','pdf','audio','template') not null,
  body text,
  media_url varchar(500) null,
  delivery_status varchar(40),
  sent_by_user_id bigint null,
  created_at datetime
);

chat_links (
  id bigint primary key,
  conversation_id bigint not null,
  entity_type enum('contact','patient','ticket','lead','home_collection','complaint') not null,
  entity_id varchar(80) not null,
  linked_by bigint not null,
  linked_at datetime not null
);

chat_ownership_history (
  id bigint primary key,
  conversation_id bigint not null,
  previous_owner_id bigint null,
  new_owner_id bigint null,
  action enum('take','reassign','override','release') not null,
  reason varchar(255) null,
  action_by bigint not null,
  action_at datetime not null
);

chat_closures (
  id bigint primary key,
  conversation_id bigint not null,
  closed_by bigint not null,
  conversation_type enum('report','invoice','lead','complaint','home_collection','doctor','pickup','other') not null,
  closure_note varchar(500) null,
  closed_at datetime not null
);

chat_tags (
  id bigint primary key,
  conversation_id bigint not null,
  tag varchar(60) not null,
  added_by bigint,
  added_at datetime
);
```

## API Endpoints

- `GET /api/chat/conversations?queue=&q=&sla=`
- `GET /api/chat/conversations/{id}`
- `POST /api/chat/conversations/{id}/take-ownership`
- `POST /api/chat/conversations/{id}/reassign`
- `GET /api/chat/conversations/{id}/messages`
- `POST /api/chat/conversations/{id}/messages`
- `POST /api/chat/conversations/{id}/internal-notes`
- `POST /api/chat/conversations/{id}/close` with required `conversation_type`
- `POST /api/chat/conversations/{id}/links`
- `DELETE /api/chat/conversations/{id}/links/{link_id}`
- `POST /api/chat/conversations/{id}/create-ticket`
- `POST /api/chat/conversations/{id}/create-lead`
- `POST /api/chat/conversations/{id}/create-home-collection`
- `GET /api/chat/conversations/{id}/audit`

## User Journeys

- New unassigned chat: agent opens Unassigned, reviews context, clicks Take Ownership, replies, links patient/contact.
- Closure: CCE clicks Close Conversation, selects conversation type such as Invoice, Report, or Lead, adds optional note, then closes. The selected type appears in the prominent tag strip and audit summary.
- Reclassification: agent changes the Conversation Type in the header when the chat context shifts, then clicks Save. The visible tag strip updates for that conversation only after save.
- Wife messaging for husband: agent links contact as wife, links husband as patient, creates report-query ticket.
- Unknown prospect: agent keeps conversation independent first, creates lead, later links home collection.
- Reply assistance: CCE can use a local dictionary for Hinglish and common lab-test spellings. The CCE emoji picker should expose only work-appropriate emojis, while inbound WhatsApp messages must support the full emoji/unicode range sent by patients.
- Supervisor override: supervisor opens Team Chats, views ownership history, reassigns with reason.
- Ticket from chat: agent opens Create Ticket drawer, sets ticket type/commitment/additional info, ticket appears immediately in right workspace.

## Wireframe Improvements

- Move away from table-only layout into faster four-surface workspace.
- Keep left queues always visible for shared inbox behavior.
- Make ownership explicit and locked before replying.
- Treat linked entities as first-class context, not hidden detail tabs.
- Use one Create action that opens a side drawer and asks what to create, reducing button clutter while avoiding full-page navigation.
- Use one Link action that opens a side drawer and asks what to link, matching the Create pattern.

## Future-Ready Extension Points

- `chat_links` supports new entity types without changing conversation ownership.
- Message table supports future template analytics, image/PDF/audio handling, and delivery callbacks.
- Ownership history supports team leader override and supervisor audits.
- Queue filters can later include AI classification, NLP routing, sentiment, and automation without changing the Phase 1 human workflow.
