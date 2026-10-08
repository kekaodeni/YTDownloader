/* URL-only companion. No page content, cookies, history or telemetry. */
(function (scope) {
  'use strict';
  const HOST = 'io.github.kekaodeni.ytdownloader';
  const api = typeof browser !== 'undefined' ? browser : chrome;
  function validUrl(value) {
    if (typeof value !== 'string' || value.length > 8192 || /[\s\\<>]/.test(value)) return false;
    try {
      const u = new URL(value), h = u.hostname.toLowerCase().replace(/\.$/, '');
      if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return false;
      if (!h.includes('.') && !h.includes(':')) return false;
      if (/\.(localhost|local|internal|lan|home|test|invalid)$/.test(h) || h === 'localhost') return false;
      if (h.includes(':')) {
        // Public IPv6 is permitted; private/mapped/loopback literals are not.
        const ip=h.replace(/^\[|\]$/g,'');
        if (!/^[23][0-9a-f]{3}:/.test(ip) || ip.startsWith('2001:db8:')) return false;
      }
      if (/^\d+\.\d+\.\d+\.\d+$/.test(h)) {
        const [a,b] = h.split('.').map(Number);
        if (a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254) ||
            (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) ||
            (a === 100 && b >= 64 && b <= 127) || (a === 198 && (b === 18 || b === 19))) return false;
      }
      return true;
    } catch (_) { return false; }
  }
  function message(action, url) {
    const result = {protocol:1, action, request_id:crypto.randomUUID().replace(/-/g,'')};
    if (action === 'send_url') result.url = url;
    return result;
  }
  async function native(action, url) {
    if (action === 'send_url' && !validUrl(url)) return {status:'invalid_url'};
    const request = message(action,url);
    try {
      const result = await api.runtime.sendNativeMessage(HOST,request);
      if (!result || result.protocol !== 1 || result.request_id !== request.request_id) return {status:'protocol_mismatch'};
      return result;
    } catch (_) { return {status:'host_unavailable'}; } // Never expose native stderr or credentials.
  }
  function statusKey(result, sending=false) {
    if (['accepted','delivered'].includes(result.status)) return sending ? 'sent' : (result.app_running ? 'connected' : 'ready');
    return ['invalid_url','app_launch_failed','protocol_mismatch','busy'].includes(result.status) ? result.status : 'host_unavailable';
  }
  function contextUrl(info, tab) { return info.menuItemId === 'send-link' ? info.linkUrl : (info.pageUrl || tab?.url); }
  scope.YTDCompanion = {api,HOST,validUrl,message,native,statusKey,contextUrl};
})(globalThis);
