# MDC Product Canon

## Mission

Mavis Digital Campus is an operating and institutional-support system for The Mavis Institute. It supports real nonprofit operations, education, farm and land stewardship, institutional memory, volunteers, projects, programs, and executive-function support. AI agents assist people; they do not replace human authority.

## Campus agents

| Agent | Product role | Campus association |
| --- | --- | --- |
| Stella | Chief of Staff | Mavis Manor |
| Percy | Director of Programs & Education | Coopenheimer Barn |
| Rose | Director of Research & Archives | Library of Mavis |
| Stewart | Land Steward | Fruit Forest & Grounds |
| Vernadette | Grants & Development Officer | Mavis Manor |
| Poe | Operations & Volunteer Coordinator | Coopenheimer Barn |

Stella's application-facing role is **Chief of Staff**. Do not replace it with EO or Executive Officer. Internal stable IDs currently include `chief`, `programs`, `research`, `caretaker`, `operations`, and `grants`.

## Campus geography

- Upper-left: Pond.
- Upper-right: Coopenheimer Barn.
- Center-left/middle: Fruit Forest.
- Lower-left: Library of Mavis.
- Lower-right: Mavis Manor.
- The map includes an S-shaped stream and crossings between Library of Mavis ↔ Fruit Forest and Fruit Forest ↔ Pond.

Do not casually rearrange locations or crossings.

## Visual identity

**Cozy 16-bit Victorian Farm.** Approved concept art and the canonical assets under `static/assets/` are the visual authority. Do not substitute a generic dashboard aesthetic without explicit instruction.

## Shared information concepts

Prefer the shared model where appropriate: Person, Project, Task, Event, Program, Work Session, Grant, Plant/Living System, Property Asset, and Document/Knowledge Item. Current implementation is authoritative: some concepts are represented directly by tables while others are represented through project, task, Library, weather/seasonal, or text metadata flows.

## Operating principles

Favor practical usefulness, understandable workflows, durable institutional memory, human oversight, incremental development, simplicity, and reliability. Human approval gates are intentional product behavior.
