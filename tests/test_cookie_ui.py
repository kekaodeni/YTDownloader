from types import SimpleNamespace


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
