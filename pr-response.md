# PR Response Doc — CineLog Watchlist Feature

## AI Usage
I used AI (Claude Code) in a few specific ways:
- **Orientation:** summarizing `models.py`, `services/collection_service.py`, and
  `tests/test_collection.py` so I understood the existing naming and dedup patterns
  before touching the watchlist code.
- **Git mechanics:** running the rebase onto `origin/main` and walking through the
  UUID conflict resolution in `models.py`, and verifying the final history had no
  merge commits and conventional-format messages.
- **Test scaffolding:** matching the fixture/assertion style of `test_collection.py`
  when writing `tests/test_watchlist.py`.
- **Stress-testing the design arguments:** for Comments 4 and 5 I wrote my position
  first, then asked what counterargument a reviewer would raise. For Comment 4 that
  surfaced the community/discovery cost of a private default, which I weighed and
  still chose privacy. The positions and reasoning in Comments 4 and 5 are my own.

## Comment 1 — Rename
**What I did:** Renamed `save_to_watchlist()` to `add_to_watchlist()` in
`services/watchlist_service.py` so it matches the project's `verb_to_noun` convention
(`add_to_collection`). Updated the one call site in `routes/watchlist/watchlist.py`
(both the import and the call inside `add_film`).
**How I verified:** Ran a project-wide search for `save_to_watchlist` — zero remaining
references. Confirmed the module and blueprint still import, and the full test suite
passed.

## Comment 2 — Deduplication
**What I did:** Followed the `add_to_collection()` pattern. Before inserting, I query
`WatchlistEntry` by `user_id` + `film_id`; if a row already exists I raise a new
`AlreadyInWatchlistError` (parallel to `AlreadyInCollectionError`) instead of creating
a duplicate. I also added a DB-level `UniqueConstraint(user_id, film_id,
name="unique_user_film_watchlist")` to `WatchlistEntry`, mirroring
`unique_user_film_collection` on `CollectionEntry`, so duplicates are impossible even
under a race.
**How I verified:** Added the same film twice — the second call raised
`AlreadyInWatchlistError` and only one row persisted. Full suite passed.

## Comment 3 — Missing test
**What I did:** Created `tests/test_watchlist.py` using the same fixtures as
`test_collection.py` (in-memory app, `sample_user`, `sample_film`). The required test,
`test_add_to_watchlist_nonexistent_film_raises`, is the equivalent of
`test_add_to_collection_nonexistent_film_raises`: it passes a UUID string that maps to
no film and asserts `FilmNotFoundError`. I also added a happy-path test and, for the
stretch, remove + edge-case tests (below).
**How I verified:** `pytest tests/test_watchlist.py -v` passed; full suite is 9/9.

**Second (self-chosen) test:** `test_remove_from_watchlist_leaves_other_entries`. I
chose this edge case because the main risk in a delete is that it's scoped too broadly
(e.g. filtered only by `user_id`), which would wipe unrelated entries. The test adds two
films, removes one, and asserts the other survives. It caught a real bug: `get_watchlist()`
called `entry.film`, but `WatchlistEntry` had no `film` relationship, so listing a
non-empty watchlist raised `AttributeError`. I fixed it by adding
`watchlist_entries = db.relationship("WatchlistEntry", backref="film")` to `Film`,
matching how `CollectionEntry` gets its `film` backref.

## Comment 4 — Default visibility
**My position:** 
Private
**Reasoning:**
--Watch list is intent, not history, this could be more revaling.
--privacy by deafult is reverable than having it public by default
**Tradeoff acknowledged:**
--There really isnt any tradefault do this nature 

## Comment 5 — Sort order
**My position:** keeping it alphabeatical 
**Reasoning:** It's the standard and most people will rember the title of a film rather than the year.
**Engagement with reviewer's point:** Date-added does make recent saves easy to spot, but a watchlist is a pick-from list you scan to find a specific film by title, not an activity feed — so alphabetical keeps things findable as it grows. The consistency with `get_collection()` is fair, but a collection logs what you've already watched (recency fits) while a watchlist is forward-looking, so ordering them differently is intentional. If users really want recency, the cleaner fix is an optional sort parameter, not changing the default.

## Comment 6 — Rebase
**What conflicted:** `models.py`. While the PR was open, `main` migrated `Film.id` from
integer to UUID (`db.String(36)`). My `WatchlistEntry.film_id` was still `db.Integer`
with a foreign key to `film.id`, and the whole `WatchlistEntry` class addition conflicted
against a `main` that didn't have the class yet.
**How I resolved it:** I kept the `WatchlistEntry` class but changed `film_id` to
`db.String(36), db.ForeignKey("film.id")` so it matches the migrated `Film.id`. I also
updated the nonexistent-film test id from the integer `999999` to a UUID string. Then
`git add models.py` and `git rebase --continue`.
**How I verified no conflict remains:** Searched the tree for conflict markers (none),
confirmed `git log --merges origin/main..HEAD` is empty (no merge commits), the branch
is linear on top of `origin/main`, and the full suite passed 9/9. I also removed the
`__pycache__/*.pyc` files that had been accidentally committed before the `.gitignore`
arrived from `main`.

## Commit History
`git log --oneline` on `feature/watchlist` after the interactive rewrite — five
conventional commits, one logical change each, no merge commits:

```
87b2c71 docs: add pr-response.md documenting code-review responses
220128c test: add watchlist service and remove edge-case tests
5ff12d3 feat: add watchlist REST endpoints
cb37393 feat: add watchlist model and service with dedup and visibility toggle
823d424 refactor: use db.session.get for film lookup in collection service
```

<!-- Replace/supplement the block above with a screenshot image of `git log --oneline`. -->
<!-- The docs commit hash shifts by one after this edit is committed; that is expected
     (a commit cannot contain a log of itself). Take the screenshot after committing. -->

## PR Description

**What the feature does**
Adds a watchlist to CineLog: films a user wants to watch later, kept separate from their
collection (films already watched). It exposes `GET /watchlist/<user_id>` to view a
watchlist and `POST /watchlist/<user_id>/add` to save a film. The service layer supports
adding (with deduplication and a visibility flag), removing, and listing entries.

**Design decisions**
1. **Default visibility = private (`public=False`).** New watchlist entries are private
   unless the caller opts in. A watchlist signals *intent*, which is more revealing than a
   log of what you've already watched, and privacy-by-default is the reversible choice.
   Callers set visibility explicitly via the `public` field on the add endpoint.
2. **Sort order = alphabetical by title.** A watchlist is a pick-from list you scan by
   title, so alphabetical stays findable as it grows. If recency is wanted later, the right
   fix is an optional sort parameter rather than changing the default.

**How to manually test**
```bash
# 1. Set up and run
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
pip install -r requirements.txt
python app.py                        # serves http://127.0.0.1:5000

# 2. In a second shell, create a user and a film and capture their UUIDs
python - <<'PY'
from app import create_app, db
from models import User, Film
app = create_app()
with app.app_context():
    u = User(username="ada", email="ada@example.com")
    f = Film(title="Arrival", year=2016, genre="Sci-Fi")
    db.session.add_all([u, f]); db.session.commit()
    print("USER", u.id); print("FILM", f.id)
PY

# 3. Add the film to the watchlist (defaults to private)
curl -X POST http://127.0.0.1:5000/watchlist/<USER_ID>/add \
     -H "Content-Type: application/json" -d '{"film_id": "<FILM_ID>"}'

# 4. Add it explicitly as public
curl -X POST http://127.0.0.1:5000/watchlist/<USER_ID>/add \
     -H "Content-Type: application/json" -d '{"film_id": "<FILM_ID>", "public": true}'

# 5. View the watchlist (alphabetical by title)
curl http://127.0.0.1:5000/watchlist/<USER_ID>
```
Automated coverage: `pytest tests/ -v` (9 tests) exercises add, deduplication,
nonexistent film, remove, remove-not-present, and the remove-leaves-others edge case.
