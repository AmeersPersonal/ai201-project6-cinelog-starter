"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service. Structured to match tests/test_collection.py —
same in-memory app fixture, same sample_user / sample_film fixtures, same
raises-based assertions.
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
    NotInWatchlistError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


@pytest.fixture
def sample_film_b(app):
    """A second film, for tests that need more than one entry."""
    with app.app_context():
        film = Film(title="Arrival", year=2016, genre="Sci-Fi")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Basic add ───────────────────────────────────────────────────────────────

def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    """
    Adding a valid film should create a WatchlistEntry in the database.
    """
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film

        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


# ── Nonexistent film ─────────────────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error.

    (Mirrors test_add_to_collection_nonexistent_film_raises. Film IDs are
    UUIDs, so the nonexistent id is a UUID string that maps to no film.)
    """
    with app.app_context():
        nonexistent_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=nonexistent_film_id)


# ── Remove ───────────────────────────────────────────────────────────────────

def test_remove_from_watchlist_deletes_entry(app, sample_user, sample_film):
    """
    Removing a film that's on the watchlist should delete its entry and
    return True. Mirrors remove_from_collection's contract.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        result = remove_from_watchlist(user_id=sample_user, film_id=sample_film)

        assert result is True
        gone = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert gone is None


def test_remove_from_watchlist_not_present_raises(app, sample_user, sample_film):
    """
    Removing a film that was never added should raise NotInWatchlistError
    rather than silently succeeding.
    """
    with app.app_context():
        with pytest.raises(NotInWatchlistError):
            remove_from_watchlist(user_id=sample_user, film_id=sample_film)


# ── Self-chosen edge case: remove is scoped to one entry ─────────────────────

def test_remove_from_watchlist_leaves_other_entries(
    app, sample_user, sample_film, sample_film_b
):
    """
    Edge case (not requested in review): removing one film must not affect
    the user's other watchlist entries. This guards against a delete that
    is scoped too broadly (e.g. filtering only by user_id). See pr-response.md
    for why this case was chosen.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)
        add_to_watchlist(user_id=sample_user, film_id=sample_film_b)

        remove_from_watchlist(user_id=sample_user, film_id=sample_film)

        remaining = get_watchlist(sample_user)
        remaining_ids = [f["id"] for f in remaining]

        assert sample_film not in remaining_ids
        assert sample_film_b in remaining_ids
        assert len(remaining) == 1
