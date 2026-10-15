import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


PAGES = ["/", "/login", "/register"]


@pytest.mark.parametrize("path", PAGES)
def test_theme_toggle_rendered_on_every_page(client, path):
    html = client.get(path).get_data(as_text=True)
    assert 'id="theme-toggle"' in html
    assert 'class="icon-sun"' in html
    assert 'class="icon-moon"' in html
    assert 'aria-label="Switch to dark mode"' in html


@pytest.mark.parametrize("path", PAGES)
def test_theme_applied_before_stylesheet(client, path):
    html = client.get(path).get_data(as_text=True)
    # The inline script must run before the stylesheet loads to avoid a flash
    assert html.index("localStorage.getItem('theme')") < html.index("css/style.css")
    assert "prefers-color-scheme: dark" in html


def test_dark_palette_defined(client):
    css = client.get("/static/css/style.css").get_data(as_text=True)
    assert ':root[data-theme="dark"]' in css
    assert "color-scheme: dark" in css
