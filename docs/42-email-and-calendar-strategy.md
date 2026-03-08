# Email And Calendar Strategy

Last updated: 2026-03-07

## Goal

Pick one clean calendar and email strategy that:

1. reduces personal scheduling mess
2. works on phone
3. remains visible in Outlook for work planning
4. gives OpenClaw a stable API target for reading and scheduling

## Email Recommendation

### Default path

1. Keep `gmail` as the main planned email/calendar integration path.
2. Reason: it aligns with Drive and Calendar, not just mail.

### Optional future path

1. Keep `agent_mail` as an optional add-in, not a default dependency.
2. Use it when the goal is a dedicated programmable inbox for the agent:
   - signups
   - notifications
   - verification emails
   - isolated outbound agent identity
3. Do not use it as the default replacement for Gmail when Drive or Calendar are part of the workflow.

## Calendar Recommendation

### Source of truth

1. Use **Google Calendar** as the single writable personal source of truth.
2. Do not use Apple Calendar as the source of truth.
3. Do not use your work Outlook calendar as the source of truth for personal scheduling.

### Why Google Calendar should be canonical

1. It is the cleanest future API target for OpenClaw.
2. It already fits the planned Google integration path in this repo.
3. It works well on phone.
4. It can be surfaced inside Outlook on the web as a connected personal calendar in many Microsoft work/school setups.

### Role of each calendar system

1. `Google Calendar`
   - canonical personal calendar
   - OpenClaw read/write target
   - personal events and planned tasks
2. `Outlook / Microsoft 365`
   - work calendar remains separate
   - use Outlook on the web combined view when allowed
3. `Apple Calendar`
   - display layer on phone only
   - not a system of record

## Practical Setup Recommendation

### Step 1: Clean ownership

1. Pick one Google account as your canonical calendar owner.
2. If Outlook combined availability matters, use the **primary calendar of that Google account** as the canonical OpenClaw target.
3. Do not make a secondary Google calendar the main OpenClaw target if you expect Outlook on the web to reflect that availability cleanly.
4. Create optional secondary calendars only if useful:
   - `OpenClaw / Tasks`
   - `Teaching`
   - `Personal`

### Step 2: Phone sanity

1. Add both your Google account and your Microsoft Exchange/Outlook account to iPhone Calendar.
2. Set the iPhone default calendar for new personal events to the Google main calendar.
3. Keep Apple Calendar as the viewer/editor, not the authority.

### Step 3: Work visibility

1. In Outlook on the web for your work/school account, try `Add calendar` -> `Add personal calendars` -> Google.
2. If your tenant allows it, this gives you a combined work + personal view and lets personal events affect work availability.
3. If your tenant does not allow it, use Outlook only for work and rely on iPhone/Google Calendar for the combined view.

### Step 4: OpenClaw integration

1. OpenClaw should read and write only to the canonical Google calendar.
2. The first OpenClaw calendar scope should be:
   - read upcoming events
   - create events with approval
   - update events with approval
3. Avoid multi-provider calendar writes in the MVP.

## What To Avoid

1. Do not try to make iCloud Calendar the central automation target.
2. Do not make OpenClaw write to both Google and Outlook from day one.
3. Do not depend on fragile cross-provider sync as your primary workflow.
4. Do not mix work-owned Outlook calendars with personal canonical scheduling unless your organization explicitly supports it.

## MVP Recommendation

1. Calendar is included in MVP.
2. MVP scope is:
   - one Google Calendar integration
   - read upcoming events
   - create/update with approval
3. Do not add Outlook calendar write support in MVP.
4. Outlook work visibility remains a display/informational concern, not an MVP write target.
