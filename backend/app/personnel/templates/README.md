# Personnel document templates

The server reads templates **only from this directory** — never from anyone's
`Downloads/` or other machine-local paths.

## Layout

- `source/` — the original documents received from the client, kept verbatim for
  reference and legal review. These are **not** wired into generation yet; they
  are the raw material for the placeholder-ready templates.
- (root) — the production `.docx` templates with `{{ placeholder }}` fields that
  the generator fills. Added one at a time as each is approved.

## `source/` provenance

| File in repo | Original name (from client) | Purpose / ТЗ ref | Status |
|---|---|---|---|
| `trudovoy_dogovor_kaz_rus.docx` | Трудовой договор (каз, рус).docx | Трудовой договор, каз/рус в двух колонках (§2.3, §4.2) | needs point fixes per §4.2 |
| `material_otvetstvennost_2006.doc` | Договор о полной материальной ответственности.doc | Договор о полной матответственности (§2.6, §4.1) | rewrite in full per §4.1 |
| `zayavlenie_priem.doc` | Заявление на прием на работу .doc | Заявление о приёме (§2.1, §4.3) | needs additions per §4.3 |
| `soglasie_personal_data.docx` | Согласие на сбор, обработку персональных данных.docx | Согласие на обработку ПД (§2.2, §4.6) | rewrite per §4.6 |
| `navigator_ku.xlsx` | Навигатор КУ.xlsx | Реестр 63 шаблонов → справочник `document_templates` (§3) | to import as registry |

## Rules

- **Legal text is provided by the client, not authored here.** We implement
  substitution only and do not change document wording. (The приём-order,
  приказ о приёме, is the one agreed exception: field set per §4.4, text
  approved by the client before it is committed as a template.)
- Editing a placeholder template is a `.docx` edit in Word — no code change and
  no app rebuild (ТЗ §6).
