Secure 360 - Backend implementation.

Event Status Table : SELECT `Eventtype`, `Eventstatus` FROM `event_status` 

Incident Record Table : SELECT `id`, `incident_date`, `incident_time`, `title`, `locationLat`, `locationLong`, `fileUploadedStatus`, `placeCityName`, `roadName`, `vehicleSpeed`, `incidentType`, `gear`, `filepath`, `created_at` FROM `incidentrecords`

Recording Status Table : SELECT `status`, `EventType`, `gear` FROM `recording_status`
