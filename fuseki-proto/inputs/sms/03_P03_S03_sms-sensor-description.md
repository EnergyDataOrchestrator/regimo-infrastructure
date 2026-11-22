# 03_P03_S03 — SMS Sensorbeschreibung (Weatherstation FS6002)

Formale Beschreibung des Szenario-Sensors aus **CF1-003** (low level Beispiel,
Messreihe Lufttemperatur) im Format des **Helmholtz Sensor Management System (SMS)**.

## Identifikation

| Feld | Wert |
|---|---|
| SMS Device | `https://sms.atmohub.kit.edu/devices/67` (Instanz: KIT AtmoHub) |
| SMS API | `https://sms.atmohub.kit.edu/backend/api/v1/devices/67` |
| Persistent Identifier (Handle) | `21.11157/9b6cdfb9-a4fb-4269-af04-1ef94588f5a8` (B2INST, EUDAT DataHub) |
| Name | KIT-CN-IAI-Bau445-Weather-Station-Weatherstation |
| Gerätetyp | Weather station (`https://sms-cv.helmholtz.cloud/sms/cv/api/v1/equipmenttypes/54/`) |
| Hersteller | FuehlerSysteme eNET International GmbH |
| Modell | FS6002 |
| Owner | Karlsruhe Institute of Technology (KIT) |
| Sichtbarkeit | öffentlich (`is_public: true`) |

## Messgröße: Lufttemperatur (Air Temperature)

SMS Device-Property **159** (`https://sms.atmohub.kit.edu/backend/api/v1/device-properties/159`):

| Feld | Wert |
|---|---|
| Property (CV) | Air temperature — `https://sms-cv.helmholtz.cloud/sms/cv/api/v1/measuredquantities/4/` |
| Einheit | °C — `https://sms-cv.helmholtz.cloud/sms/cv/api/v1/units/51/` |
| Messbereich (SMS) | −80.0 … 60.0 °C ⚠️ (siehe Diskrepanz unten) |
| Sampling Media | Air (`.../samplingmedia/9/`) |
| Compartment | Atmosphere (`.../compartments/1/`) |
| Aggregation | Average (`.../aggregationtypes/1/`) |
| Accuracy (SMS) | *nicht dokumentiert* (`null`) |
| Resolution (SMS) | *nicht dokumentiert* (`null`) |
| Label | Air Temperature |

## Genauigkeit & Auflösung (Autorität: Datenblatt)

Quelle: **Bedienungsanleitung Wetterstation FS6002** (im SMS als
Device-Attachment 395 hinterlegt, S. 66 „Technische Daten“ —
`https://sms.atmohub.kit.edu/backend/api/v1/device-attachments/395/file/bedienungsanleitung_fs6002_deu.pdf`):

- **Messbereich:** −40 … +80 °C
- **Genauigkeit:** ±0.3 K @ 25 °C; ±1.0 K über −40 … +80 °C
- **Auflösung:** 0.1 K

## Diskrepanz: Messbereich

Der im SMS-Eintrag hinterlegte Messbereich (−80 … 60 °C) weicht vom
Datenblatt (−40 … +80 °C) ab. Das Datenblatt ist die Autorität. Der
SMS-Eintrag sollte korrigiert werden; bis dahin gilt für EDO:
**Messbereich gemäß Datenblatt −40 … +80 °C**.

## Weiterführende Eigenschaften des Geräts (Device-Properties 157–161)

| ID | Property | Einheit | Messbereich (SMS) | Messgröße (CV) | Aggregation |
|---|---|---|---|---|---|
| 157 | Wind speed | m/s | 0.0 … 75.0 | `.../measuredquantities/172/` | Average |
| 158 | Wind direction | ° | 0.0 … 360.0 | `.../measuredquantities/170/` | Circular maximum distribution |
| 159 | **Air temperature** | °C | −80.0 … 60.0 ⚠️ | `.../measuredquantities/4/` | Average |
| 160 | Relative humidity | % | 0.0 … 100.0 | `.../measuredquantities/124/` | Average |
| 161 | Atmospheric pressure | hPa | 500.0 … 1200.0 | `.../measuredquantities/3/` | Average |

### Aggregation/Resolution-Hinweise (2026-11-19, Export F7)

- **158 (Wind direction):** Aggregationstyp `Circular maximum distribution` (`.../aggregationtypes/8/`) — kein arithmetisches Mittel.
- **161 (Atmospheric pressure):** einziges Property mit **Resolution** `0.1 hPa` (`.../units/57/`); alle übrigen `null`.
- Alle fünf Properties referenzieren Kompartiment `Atmosphere` (`.../compartments/1/`) und Sampling-Media `Air` (`.../samplingmedia/9/`).

## Maschinenlesbare Repräsentation

- `device-67.json` — vollständiger SMS-API-Datensatz des Geräts (JSON:API)
- `device-67-property-157-wind-speed.json` — Wind Speed (m/s)
- `device-67-property-158-wind-direction.json` — Wind Direction (°)
- `device-67-property-159-air-temperature.json` — Air Temperature (°C)
- `device-67-property-160-relative-humidity.json` — Relative Humidity (%)
- `device-67-property-161-atmospheric-pressure.json` — Atmospheric Pressure (hPa)

> Alle fünf Device-Property-Dateien (157–161) sind seit 2026-11-19 (F7) exportiert;
> die Schnittmenge mit den in `device-67.json` referenzierten `device_properties`-ids
> ist vollständig (verifiziert). Damit ist die **maschinenlesbare Sensorabdeckung des
> FS6002 vollständig** im SMS-Originalformat. Nur Air Temperature (159) trägt die
> Datenblatt-Autorität (Messbereich −40 … +80 °C, siehe Diskrepans oben).

Diese Dateien sind die „formale SMS-Beschreibung“ im Originalformat des SMS.

## Bezug zum EDO-Workflow

- Szenario/Zeitrahmen/Sampling: siehe `01_Definition_low_level_Beispiel.md`
  (Messreihe Lufttemperatur, 15-minütiges Sampling-Intervall, 2026-07-01 … 2026-09-30)
- Der SMS-Eintrag ist eine der Informationsquellen (neben DMP/RDMO) für das
  interne Format (CF1-006) und deren LinkML-Schemata (CF1-007).
