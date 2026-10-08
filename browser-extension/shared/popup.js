'use strict';
const {api,native,validUrl,statusKey} = YTDCompanion;
let activeUrl = '';
document.documentElement.lang = api.i18n.getUILanguage();
for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = api.i18n.getMessage(element.dataset.i18n);
const send = document.getElementById('send');
function show(result,sending=false) {
  const key = statusKey(result,sending);
  document.getElementById('status').textContent = api.i18n.getMessage(key);
  document.getElementById('dot').className = ['sent','connected','ready'].includes(key) ? 'connected' : '';
}
(async () => {
  try {
    const [tab] = await api.tabs.query({active:true,currentWindow:true});
    activeUrl = tab?.url || '';
    document.getElementById('url').textContent = activeUrl;
    document.getElementById('domain').textContent = validUrl(activeUrl) ? new URL(activeUrl).hostname : api.i18n.getMessage('invalid_url');
    send.disabled = !validUrl(activeUrl);
    show(await native('ping'));
  } catch (_) { show({status:'host_unavailable'}); }
})();
send.addEventListener('click',async () => {
  send.disabled = true;
  document.getElementById('status').textContent = api.i18n.getMessage('sending');
  show(await native('send_url',activeUrl),true);
  send.disabled = !validUrl(activeUrl);
});
