# Discord Notification Design

Japanese version: [jp/DISCORD_NOTIFICATION_DESIGN.md](jp/DISCORD_NOTIFICATION_DESIGN.md)

## Goal

Discord notifications must help a grower complete the next action. They are not
a replacement for Hub logs. A useful notification answers three questions in
this order:

1. What needs attention?
2. Where and for which crop or device?
3. Which Hub screen completes the check?

## Delivery policy

- Plant tasks are aggregated into at most one digest at 04:00 Asia/Tokyo.
- The digest groups tasks as today, advance reminder, and newly added.
- An advance reminder is sent once, exactly the configured number of days
  before `window_start`; it is not repeated throughout the lead window.
- Start-day and remaining-window reminders are independent preferences.
- A task shown as today or advance is not duplicated in the new-task group.
- The digest shows up to six action cards. Additional work stays available in
  the annual cultivation calendar.
- MQTT activity notifications are an advanced troubleshooting option and are
  disabled by default.

The six-card limit also leaves room below Discord's current limits of ten
embeds per webhook message and 6,000 combined embed characters. See the
[Discord Webhook Resource](https://docs.discord.com/developers/resources/webhook)
and [Message Resource](https://docs.discord.com/developers/resources/message).

## Action links

Notification links must use only a validated HTTPS Cloudflare hostname from:

1. `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`
2. `CLOUDFLARE_TUNNEL_HOSTNAME`

The service never falls back to request hosts, localhost, `.local` names, or IP
addresses. If no valid public hostname is configured, a notification may still
be sent, but it contains no misleading link.

Plant task links open the exact action:

```text
/fields/{field_id}/calendar?planting={planting_id}&action={action_id}
```

Device alerts open the relevant device tab, such as overview, settings, or
diagnostics.

## Administrator controls

The Hub application settings provide:

- a master switch that pauses every Discord notification while preserving
  per-type preferences;
- an explicit, confirmed "disable all" action;
- plant-task digest, new-task, advance-day, start-day, and active-window
  preferences;
- new-device, offline-device, missing-watering, and calibration suggestions;
- MQTT activity under advanced settings.

`DISCORD_WEBHOOK_URL` remains infrastructure configuration. It is never shown
or persisted in the runtime settings file.

## Existing database compatibility

Runtime settings are merged with defaults. Existing `config.json` files that do
not contain the `discord` section therefore continue to load. Notification
preferences are written only after an administrator saves them. The webhook
URL is excluded by the runtime allowlist.

