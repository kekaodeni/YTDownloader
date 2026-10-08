if (typeof importScripts === 'function') importScripts('core.js');
const {api,native,statusKey,contextUrl} = YTDCompanion;
api.runtime.onInstalled.addListener(async () => {
  await api.contextMenus.removeAll();
    api.contextMenus.create({id:'send-page',title:api.i18n.getMessage('send_page'),contexts:['page']});
    api.contextMenus.create({id:'send-link',title:api.i18n.getMessage('send_link'),contexts:['link']});
});
api.contextMenus.onClicked.addListener(async (info,tab) => {
  const result = await native('send_url',contextUrl(info,tab));
  const key = statusKey(result,true), ok = key === 'sent';
  await api.action.setBadgeText({text:ok ? '✓' : '!'});
  await api.action.setBadgeBackgroundColor({color:ok ? '#1667ce' : '#ad3131'});
  await api.action.setTitle({title:api.i18n.getMessage(key)});
});
