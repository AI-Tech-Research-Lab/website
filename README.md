# AI-Tech Research Lab website

The static website is served by GitHub Pages. Publications are updated locally;
running the updater does not commit or publish changes.

Activities are curated separately from the lab's LinkedIn posts. See the
[editorial source notes](docs/activities-sources.md) for the selected events,
dates and supporting links.

## Update publications

Requires Python 3.10+ and `curl` (used for Google Scholar).

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python script.py
```

The updater uses the verified OpenAlex author IDs in `data/members.json` for
current and former lab members. It includes their publications
from the last ten calendar years (2017–2026 in 2026), including work predating
membership of the lab. Edit that file when the team changes. Names alone are not
safe identifiers: Luca Colombo, for example, has several unrelated namesakes.

Members with `"active": false` are retained for publication retrieval, even when
their card has been removed from `pages/team.html`. Missing `active` means active.
The Team page is maintained separately; changing this flag alone does not render
or remove a card.

OpenAlex is the primary source. The complete Manuel Roveri Scholar profile is
also fetched and compared, adding titles missing from OpenAlex. Scholar searches
for the other members are currently blocked, so this is not an exact mirror of
all members' Scholar profiles. OpenAlex may have indexing delays or attribution
errors; some Scholar-only records have abbreviated authors or venues, as displayed
on Scholar. Each entry links to its DOI, original source or Scholar record.

Entries are merged by DOI or normalized title, ignoring case, punctuation,
accents and a leading “The”. Published versions take precedence over preprints.
Different titles remain separate to avoid merging distinct papers automatically.
Preprints are marked. Existing non-paper records in the sources, such as patents
and theses, are retained, consistent with the previous Scholar-based list.

The script saves the bibliography and coverage report in `data/publications.json`,
and Scholar's supplementary records in `data/scholar-roveri.json`. If Scholar blocks
a refresh, it reuses that dated cache and prints a warning. If OpenAlex fails or
returns an empty list, the page is preserved and the command exits with an error.
HTML metadata is escaped; updates validate the markers and replace files atomically.

```sh
# Preview counts without modifying any files
.venv/bin/python script.py --dry-run

# Choose the earliest publication year explicitly
.venv/bin/python script.py --since 2020

# Regenerate HTML from the saved bibliography, with no network access
.venv/bin/python script.py --offline

# Run the regression checks
.venv/bin/python -m unittest discover -s tests -v
```

Offline rendering can only use the years contained in the saved snapshot.
Commands work from any directory. An optional `OPENALEX_API_KEY` environment
variable can be used if the shared unauthenticated API quota is exhausted.
API keys are neither stored in the generated files nor printed in errors.

Source documentation: [OpenAlex authors](https://help.openalex.org/data/authors/),
[OpenAlex works](https://help.openalex.org/data/works/).
