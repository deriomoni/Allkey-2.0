# Personnel module (Кадровые документы)

Stateless HR-document generator. Employees' personal data is never stored — it
lives in the client draft and is POSTed only to render documents. Only `Company`
(employer requisites) and `DocumentTemplate` are persisted. See
[`templates/README.md`](templates/README.md) for the template library and rules.

## ⚠️ Kazakh column — proofread before sale

The Kazakh side of the bilingual трудовой договор (and any future bilingual
document) is assembled from helpers (numbers/dates/term), reference dictionaries
(`kk_dictionaries.py`) and manually-entered translations. **It must be proofread
by a native Kazakh speaker before the module is used with real clients.** Do not
release bilingual output to clients until that proofreading is done. The
`signer_basis_kz` mapping in particular is approximate.

## Reserved names — pitfalls to avoid

Names that silently mean something else in the tools we use. **Do not** use them
as field/key names in the places noted. Append every new case you hit.

| Name | Where it bites | Symptom | Do this instead |
|---|---|---|---|
| `date` | a **pydantic** model field (`date: Optional[date]`) | the field name shadows the imported type → the annotation resolves to `NoneType`, so any non-null value fails validation (`Input should be None`) | name the field `doc_date` (we do this in `LiabilityIn`/`NonCompeteIn`/`ActIn`/`PerechenIn`) |
| `items`, `keys`, `values`, `get` | a **dict key** read via dot-access in a Jinja/docxtpl context (`{{ obj.items }}`) | Jinja tries `getattr` first, so it returns the **dict method** (`<built-in method items>`), not your value | don't name context keys this way; if unavoidable, expose them as top-level context variables (a bare `{% for it in items %}` resolves from the context, not via attribute access) or rename the key |

> When you discover another reserved-name trap, add a row here with the trigger,
> the symptom, and the fix — so the next person doesn't rediscover it.
