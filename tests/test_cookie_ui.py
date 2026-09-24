from types import SimpleNamespace

from conftest import click_item, find_item


def test_cookie_profile_can_be_disabled_without_losing_saved_profile(qapp):
    from yt_downloader.ui.quick_cookies import CookiePresenter
    from yt_downloader.core.models import CookieProfile
    presenter = CookiePresenter()
    profile = CookieProfile('one', 'YouTube / Firefox', 'browser', browser='firefox', domain_hint='youtube.com')
    presenter.set_profiles((profile,))
    assert presenter.selected_profile is None
    presenter.selectProfile(1)
    assert presenter.selected_profile == profile
    presenter.selectProfile(0)
    assert presenter.selected_profile is None
    assert presenter.profiles == (profile,)


def test_cookie_required_keeps_url_and_exposes_retry(qapp):
    from yt_downloader.app import AppController
    from yt_downloader.core.errors import AppError
    from yt_downloader.ui.quick_cookies import CookiePresenter
    controller = AppController.__new__(AppController)
    cookies = CookiePresenter()
    controller.window = SimpleNamespace(cookies=cookies)
    errors = []
    controller.show_error = errors.append
    error = AppError('COOKIE_REQUIRED', '请配置 Cookie', 'provider requested cookies')
    controller._apply_metadata_error(error)
    assert cookies.state['authRequired']
    assert errors == [error]  # technical details stay copyable


def test_cookie_modes_and_saved_profiles_are_explicit(qapp):
    from yt_downloader.ui.quick_cookies import CookiePresenter
    from yt_downloader.core.models import CookieProfile

    presenter = CookiePresenter()
    assert [item['id'] for item in presenter.state['modeOptions']] == ['none', 'browser', 'file']
    assert presenter.state['modeOptions'][1]['description']
    profile = CookieProfile('one', 'YouTube / Firefox', 'browser', browser='firefox', domain_hint='youtube.com')
    presenter.set_profiles((profile,))
    assert presenter.state['profileCards'][0]['id'] == 'one'
    assert presenter.state['profileCards'][0]['summary'] == 'Firefox · youtube.com'
    presenter.selectProfile(1)
    assert presenter.state['source'] == 'browser'


def test_cookie_delete_requires_confirmation_before_mutation(qapp):
    from yt_downloader.ui.quick_cookies import CookiePresenter
    from yt_downloader.core.models import CookieProfile

    presenter = CookiePresenter()
    profile = CookieProfile('one', 'Fixture', 'browser', browser='edge')
    presenter.set_profiles((profile,))
    presenter.selectProfile(1)
    requests = []
    presenter.delete_requested.connect(requests.append)
    presenter.removeProfile()
    assert requests == [profile]
    assert presenter.profiles == (profile,)


def test_cookie_switch_routes_by_site_and_off_is_anonymous(qapp):
    from yt_downloader.ui.quick_cookies import CookiePresenter
    from yt_downloader.ui.quick_download import DownloadPresenter
    from yt_downloader.core.models import CookieProfile

    cookies = CookiePresenter()
    page = DownloadPresenter('', None)
    edge = CookieProfile('edge', 'YouTube - Edge', 'browser', browser='edge', domain_hint='youtube.com')
    x = CookieProfile('x', 'X / Firefox', 'browser', browser='firefox', domain_hint='twitter.com')
    cookies.set_profiles((edge, x))
    page.set_cookie_state(cookies.profiles)
    page.set_url('https://youtu.be/fixture')
    assert page.selected_cookie_profile(cookies) is None
    page.setCookieEnabled(True)
    assert page.selected_cookie_profile(cookies) == edge
    page.set_url('https://x.com/fixture/status/1')
    assert page.selected_cookie_profile(cookies) == x
    page.setCookieEnabled(False)
    assert page.selected_cookie_profile(cookies) is None


def test_cookie_editor_preserves_browser_profile_and_delete_is_scoped(qapp):
    from yt_downloader.ui.quick_cookies import CookiePresenter
    from yt_downloader.core.models import CookieProfile

    presenter = CookiePresenter()
    browser = CookieProfile('one', 'Edge', 'browser', browser='edge', domain_hint='example.org', browser_profile='Default')
    presenter.set_profiles((browser,))
    saved = []
    presenter.save_requested.connect(saved.append)
    presenter.editor_requested.connect(lambda profile: None)
    presenter.saveEditor({'id': 'one', 'name': 'Renamed', 'source': 'browser', 'browser': 'firefox',
                          'browser_profile': 'Profile 1', 'domain': 'example.org'})
    assert saved and saved[-1][0].name == 'Renamed'
    assert saved[-1][0].browser_profile == 'Profile 1'
    presenter.apply_saved_profiles(())
    assert presenter.profiles == ()


def test_cookie_conflict_blocks_parse_without_guessing(qapp):
    from yt_downloader.ui.quick_download import DownloadPresenter
    from yt_downloader.core.models import CookieProfile
    page = DownloadPresenter('', None)
    page.set_cookie_state((CookieProfile('a', 'One', 'browser', browser='firefox', domain_hint='x.com'),
                           CookieProfile('b', 'Two', 'browser', browser='edge', domain_hint='twitter.com')))
    page.set_url('https://x.com/post/1')
    page.setCookieEnabled(True)
    requests = []
    page.parse_requested.connect(requests.append)
    page.requestParse()
    assert requests == []
    assert '多份' in page.state['cookieHint']


def test_cookie_profile_change_invalidates_parsed_media_and_task_snapshot(qapp, tmp_path):
    from yt_downloader.ui.quick_download import DownloadPresenter
    from yt_downloader.core.models import CookieProfile
    from test_download_service import _request
    page = DownloadPresenter(str(tmp_path), None)
    original = CookieProfile('x', 'X', 'browser', browser='firefox', domain_hint='x.com')
    replacement = CookieProfile('b', 'Bili', 'browser', browser='edge', domain_hint='bilibili.com')
    page.set_cookie_state((original,))
    page.set_url('https://x.com/post/1')
    page.setCookieEnabled(True)
    page.requestParse()
    assert page.selected_cookie_profile(None) == original
    page.show_video(_request(tmp_path).video)
    assert page.state['ready'] is True
    page.set_cookie_state((replacement,))
    assert page.state['ready'] is False
    assert page.selected_cookie_profile(None) is None


def test_cookie_editor_save_failure_keeps_original_profile(qapp):
    from yt_downloader.ui.quick_cookies import CookiePresenter
    from yt_downloader.core.models import CookieProfile
    presenter = CookiePresenter()
    original = CookieProfile('one', 'Original', 'browser', browser='firefox', domain_hint='x.com')
    presenter.set_profiles((original,))
    presenter.save_requested.connect(lambda _profiles: presenter.mark_save_failed())
    assert presenter.saveEditor({'id': 'one', 'name': 'Changed', 'source': 'browser',
                                 'browser': 'firefox', 'domain': 'x.com'}) is False
    assert presenter.profiles == (original,)


def test_cookie_settings_help_and_editor_source_fields_are_interactive(quick_window, qtbot):
    quick_window._select_page(2)
    help_button = find_item(quick_window, 'cookiePrivacyHelp')
    assert help_button.isVisible() and help_button.isEnabled()
    click_item(quick_window, help_button)
    qtbot.waitUntil(lambda: any(s.state['kind'] == 'info' for s in quick_window.dialogs.sessions))
    info = next(s for s in quick_window.dialogs.sessions if s.state['kind'] == 'info')
    assert '敏感凭据' in info.state['message']
    info.reject()

    quick_window.cookies.newProfile()
    session = quick_window.cookies._editor_session
    qtbot.waitUntil(lambda: find_item(quick_window, 'cookieSourceCombo').isVisible())
    assert session.state['source'] == 'browser'
    assert find_item(quick_window, 'cookieBrowser').isVisible()
    assert find_item(quick_window, 'cookieBrowserProfile').isVisible()
    assert not find_item(quick_window, 'cookieBrowse').isVisible()

    session.setSource('file')
    qtbot.waitUntil(lambda: find_item(quick_window, 'cookieBrowse').isVisible())
    assert not find_item(quick_window, 'cookieBrowser').isVisible()
    assert not find_item(quick_window, 'cookieBrowserProfile').isVisible()

    session.setSource('browser')
    qtbot.waitUntil(lambda: find_item(quick_window, 'cookieBrowser').isVisible())
    assert not find_item(quick_window, 'cookieBrowse').isVisible()
