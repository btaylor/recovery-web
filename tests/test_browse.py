from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app import create_app
from app.config import Config
from app.routes import PAGE

ENV = {"ND_URL": "http://nd:4533", "ND_USER": "u", "ND_PASS": "p"}


def album(i):
    return NS(id=f"a{i}", name=f"Album {i}", artist="Artist", cover_art=f"c{i}")


@pytest.fixture
def client():
    app = create_app(Config.from_env(ENV))
    nd = app.extensions["nd"] = MagicMock()
    nd.get_genres.return_value = [NS(value="Ambient", album_count=2), NS(value="Jazz", album_count=9),
                                  NS(value="Empty", album_count=0)]
    nd.get_album_list2.side_effect = lambda *a, **k: [album(i) for i in range(k["size"])]
    return app.test_client(), nd


def test_index_renders_wall_genres_by_size_and_hides_empty(client):
    c, nd = client
    html = c.get("/").text
    assert html.count('class="tile"') == PAGE
    assert html.index("Jazz") < html.index("Ambient") and "Empty" not in html
    assert "9 albums" in html and "/cover/c0?size=300" in html
    nd.get_album_list2.assert_called_with("alphabeticalByArtist", size=PAGE, offset=0)


def test_full_page_has_infinite_scroll_sentinel(client):
    c, _ = client
    assert f'hx-get="/albums?offset={PAGE}"' in c.get("/").text


def test_last_partial_page_has_no_sentinel(client):
    c, nd = client
    nd.get_album_list2.side_effect = lambda *a, **k: [album(1)]
    assert "sentinel" not in c.get("/albums?offset=48").text


def test_genre_filter_and_paging_keep_the_genre(client):
    c, nd = client
    html = c.get("/albums?genre=Jazz&offset=48").text
    nd.get_album_list2.assert_called_with("byGenre", size=PAGE, offset=48, genre="Jazz")
    assert f"offset={2 * PAGE}&genre=Jazz" in html
    assert "hx-swap-oob" not in html  # only the first page updates the pinned chip


def test_first_page_updates_pinned_genre_chip(client):
    c, _ = client
    assert 'id="current"' in c.get("/albums?genre=Jazz").text


def test_search_uses_search3_and_overrides_genre(client):
    c, nd = client
    nd.search3.return_value = NS(album=[album(1)])
    html = c.get("/albums?q=blue&genre=Jazz").text
    nd.search3.assert_called_with("blue", artist_count=0, song_count=0, album_count=PAGE, album_offset=0)
    assert html.count('class="tile"') == 1 and ">blue<" in html


def test_empty_results_message(client):
    c, nd = client
    nd.search3.return_value = NS(album=None)
    assert "No albums matching" in c.get("/albums?q=zzz").text
