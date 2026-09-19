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
