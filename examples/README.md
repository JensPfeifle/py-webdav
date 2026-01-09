# Example CalDAV and CardDAV Data

This directory contains example calendar and contact data that can be used to test the CalDAV and CardDAV server implementation.

## Directory Structure

```
examples/
├── calendars/
│   ├── work/
│   │   ├── .metadata.json         # Calendar metadata
│   │   ├── team-meeting.ics       # Recurring weekly meeting
│   │   ├── project-review.ics     # One-time event with attendees
│   │   └── code-review.ics        # TODO item
│   └── personal/
│       ├── .metadata.json         # Calendar metadata
│       ├── dentist-appointment.ics # Event with alarm
│       └── birthday-party.ics     # All-day event
└── contacts/
    └── personal/
        ├── .metadata.json         # Address book metadata
        ├── john-doe.vcf           # Complete contact with work/home info
        ├── alice-smith.vcf        # Professional contact
        ├── bob-johnson.vcf        # Freelancer contact
        ├── sarah-williams.vcf     # Friend contact
        └── mike-tech-support.vcf  # Service provider contact
```

## Usage

### Start the server with CalDAV and CardDAV enabled:

```bash
py-webdav-server --caldav --carddav examples/
```

The server will be available at:
- **CalDAV**: http://localhost:8080/.well-known/caldav
- **CardDAV**: http://localhost:8080/.well-known/carddav

### Access calendars:

- Work Calendar: http://localhost:8080/calendars/work/
- Personal Calendar: http://localhost:8080/calendars/personal/

### Access contacts:

- Personal Contacts: http://localhost:8080/contacts/personal/

## Testing with CalDAV/CardDAV Clients

### macOS Calendar and Contacts

1. Open **Calendar** or **Contacts** app
2. Add a new CalDAV/CardDAV account:
   - Account Type: Manual
   - Server: `http://localhost:8080`
   - Username: (any)
   - Password: (any)

### Thunderbird with Lightning

1. Install Lightning add-on
2. Add Network Calendar:
   - Location: `http://localhost:8080/calendars/work/`
   - Format: CalDAV

### curl examples

```bash
# List calendars
curl -X PROPFIND http://localhost:8080/calendars/ -H "Depth: 1"

# Get a specific event
curl http://localhost:8080/calendars/work/team-meeting.ics

# List contacts
curl -X PROPFIND http://localhost:8080/contacts/personal/ -H "Depth: 1"

# Get a specific contact
curl http://localhost:8080/contacts/personal/john-doe.vcf
```

## Calendar Events

### Work Calendar
- **team-meeting.ics**: Recurring weekly team meeting every Wednesday
- **project-review.ics**: Quarterly project review with multiple attendees
- **code-review.ics**: TODO item for code review task

### Personal Calendar
- **dentist-appointment.ics**: Appointment with 1-hour reminder alarm
- **birthday-party.ics**: All-day event for birthday celebration

## Contacts

- **john-doe.vcf**: Complete contact with work/home emails, phones, and addresses
- **alice-smith.vcf**: Medical professional with work contact info
- **bob-johnson.vcf**: Freelance designer with minimal info
- **sarah-williams.vcf**: Friend with personal contact details
- **mike-tech-support.vcf**: Service provider with business contact

## File Formats

### Calendar Metadata (.metadata.json)
```json
{
  "name": "Calendar Name",
  "description": "Calendar description",
  "max_resource_size": 0,
  "supported_component_set": ["VEVENT", "VTODO"]
}
```

### Address Book Metadata (.metadata.json)
```json
{
  "name": "Address Book Name",
  "description": "Address book description",
  "max_resource_size": 0
}
```

### iCalendar Format (.ics)
Standard RFC 5545 iCalendar format supporting:
- VEVENT (events)
- VTODO (tasks)
- VALARM (reminders)
- RRULE (recurrence rules)

### vCard Format (.vcf)
Standard RFC 6350 vCard 3.0 format supporting:
- Personal information (name, birthday)
- Contact methods (email, phone)
- Addresses (home, work)
- Organization details
- Notes and categories
