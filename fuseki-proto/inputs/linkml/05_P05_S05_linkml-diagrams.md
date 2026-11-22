# 05_P05_S05 — LinkML-Diagramme (CF1-007)

Status: ✅
Datum: 2026-11-19

Mermaid-ER-Diagramme der drei LinkML-Schemas (Klassen mit Slots/Ranges, Beziehungen mit Kardinalitäten). Die `.mmd`-Dateien liegen daneben; die Diagramme unten rendern direkt in Obsidian.

## DMP-Schema (`05_P05_S05_madmp-schema.yaml`, 10 Klassen)

```mermaid
erDiagram
Contact {
    string name
    uriorcurie mbox
}
Contributor {
    string name
    uriorcurie mbox
    string role
    string set
}
Cost {
    string currency
    string title
    decimal value
}
DMP {
    date created
    LanguageEnum language
    date modified
    string title
}
Dataset {
    string description
    stringList data_quality_assurance
    date issued
    stringList keyword
    LanguageEnum language
    boolean personal_data
    string preservation_statement
    boolean sensitive_data
    string title
    string type
}
Distribution {
    uriorcurie access_url
    CertificationEnumList certified_with
    DataAccessEnum data_access
    stringList format
    uriorcurie license_ref
    date license_start_date
    IdentifierTypeEnumList pid_system
    string title
}
Host {
    string title
    uriorcurie url
}
Identifier {
    string identifier
    IdentifierTypeEnum type
}
Project {
    string description
    date end
    date start
    string title
}
SecurityAndPrivacy {
    string description
    string title
}

Contact ||--|o Identifier : "contact_id"
Contributor ||--|o Identifier : "contributor_id"
DMP ||--|o Contact : "contact"
DMP ||--|o Project : "project"
DMP ||--|| Identifier : "dmp_id"
DMP ||--}o Contributor : "contributor"
DMP ||--}o Cost : "cost"
DMP ||--}o Dataset : "dataset"
Dataset ||--|o Identifier : "dataset_id"
Dataset ||--}o Distribution : "distribution"
Dataset ||--}o SecurityAndPrivacy : "security_and_privacy"
Distribution ||--|o Host : "host"
```

## SMS-Schema (`05_P05_S05_sms-schema.yaml`, 2 Klassen)

```mermaid
erDiagram
Device {
    string id
    string description
    boolean archived
    datetime created_at
    string device_type_name
    uriorcurie device_type_uri
    boolean is_internal
    boolean is_private
    boolean is_public
    string long_name
    string manufacturer_name
    string model
    string persistent_identifier
    string serial_number
    string short_name
    uriorcurie status_uri
    datetime updated_at
    uriorcurie website
}
DeviceProperty {
    string id
    string description
    double accuracy
    string accuracy_unit_name
    uriorcurie accuracy_unit_uri
    string aggregation_type_name
    uriorcurie aggregation_type_uri
    string compartment_name
    uriorcurie compartment_uri
    datetime created_at
    double failure_value
    string label
    double measuring_range_max
    double measuring_range_min
    string property_name
    uriorcurie property_uri
    double resolution
    string resolution_unit_name
    uriorcurie resolution_unit_uri
    string sampling_media_name
    uriorcurie sampling_media_uri
    string unit_name
    uriorcurie unit_uri
    datetime updated_at
}

Device ||--}o DeviceProperty : "device_properties"
```

## Internes-Format-Schema (`05_P05_S05_internal-format-schema.yaml`, 14 Klassen)

```mermaid
erDiagram
Contribution {
    ContributorTypeEnum role
}
Cost {
    string currency
    string title
    decimal value
}
Dataset {
    string description
    string dataset_type
    date issued
    stringList keyword
    boolean personal_data
    string preservation_statement
    stringList quality_assurance
    boolean sensitive_data
    string title
}
Distribution {
    uriorcurie access_url
    CertificationEnumList certified_with
    DataAccessEnum data_access
    stringList format
    date license_start_date
    IdentifierTypeEnumList pid_system
    string title
}
Host {
    string title
    uriorcurie url
}
Identifier {
    IdentifierTypeEnum identifier_type
    string identifier_value
}
Interval {
    date interval_begin
    date interval_end
}
License {
    date license_start_date
    uriorcurie license_uri
}
MeasuredProperty {
    string accuracy
    uriorcurie aggregation_type
    uriorcurie compartment
    uriorcurie measured_quantity
    string measured_quantity_name
    double measuring_range_max
    double measuring_range_min
    double resolution
    uriorcurie sampling_media
    uriorcurie unit
}
MeasurementSeries {
    string title
}
Person {
    string name
    uriorcurie mbox
}
Project {
    string description
    string language
    string title
}
SamplingPlan {
    string sampling_interval
    uriorcurie sampling_media
}
Sensor {
    string manufacturer
    string model
    uriorcurie sensor_type
    string title
}

Contribution ||--|o Person : "agent"
Dataset ||--|o Identifier : "identifier"
Dataset ||--|o MeasurementSeries : "realized_as"
Dataset ||--|o Sensor : "was_generated_by"
Dataset ||--}o Distribution : "has_distribution"
Dataset ||--}o MeasuredProperty : "observes"
Distribution ||--|o Host : "hosted_by"
Distribution ||--|o License : "license"
MeasurementSeries ||--|o Interval : "interval"
MeasurementSeries ||--|o SamplingPlan : "has_sampling_plan"
MeasurementSeries ||--|o Sensor : "was_generated_by"
Person ||--|o Identifier : "identifier"
Project ||--|o Identifier : "dmp_id"
Project ||--|o Interval : "interval"
Project ||--|o Person : "has_contact"
Project ||--}o Contribution : "has_contribution"
Project ||--}o Cost : "has_cost"
Project ||--}o Dataset : "has_dataset"
Sensor ||--|o Identifier : "identifier"
Sensor ||--}o MeasuredProperty : "observes"
```

## Regenerierung

```sh
cd projecting_spaces/EDO/Artefacts/07_Fragments/scripts/linkml
PY=/Users/ot2661/Documents/01_dev/edo/.venv/bin/python3
for s in madmp sms internal-format; do
  PYTHONPATH=/tmp/linkmllib $PY -m linkml.generators.erdiagramgen "05_P05_S05_${s}-schema.yaml" > "05_P05_S05_${s}-erd.mmd"
done
```

Pro-Klassen-Diagramme (eine Mermaid-Datei je Klasse):

```sh
PYTHONPATH=/tmp/linkmllib $PY -m linkml.generators.mermaidclassdiagramgen -d /tmp/mmout <schema>.yaml
```

Graphviz-Variante (veraltet, rendert direkt via `dot`, hängt die Format-Endung an `-o` an):

```sh
PYTHONPATH=/tmp/linkmllib $PY -m linkml.generators.dotgen <schema>.yaml -o <name> -f dot
dot -Tsvg <name>.dot -o <name>.svg
```

Hinweis: `range: Any` ist ohne eigene `Any`-Klasse kein gültiger Range — `erdiagramgen`/`dotgen` brechen mit „unrecognized range (Any)“ ab, während `jsonschemagen` stillschweigend durchläuft. URI-artige Felder stehen deshalb auf `uriorcurie` (siehe Modellentscheidungen §5).
