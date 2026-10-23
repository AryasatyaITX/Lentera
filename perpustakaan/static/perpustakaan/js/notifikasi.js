(() => {
  const locale = navigator.language || 'en';
  let formatter;
  try {
    formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'narrow' });
  } catch {
    formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'narrow' });
  }

  function relativeLabel(date) {
    const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
    if (seconds < 45) return formatter.format(0, 'second');
    if (seconds < 3600) return formatter.format(-Math.floor(seconds / 60), 'minute');
    if (seconds < 86400) return formatter.format(-Math.floor(seconds / 3600), 'hour');
    if (seconds < 604800) return formatter.format(-Math.floor(seconds / 86400), 'day');
    if (seconds < 2629800) return formatter.format(-Math.floor(seconds / 604800), 'week');
    if (seconds < 31557600) return formatter.format(-Math.floor(seconds / 2629800), 'month');
    return formatter.format(-Math.floor(seconds / 31557600), 'year');
  }

  function updateRelativeTimes() {
    document.querySelectorAll('[data-relative-time]').forEach((element) => {
      const date = new Date(element.dateTime);
      if (!Number.isNaN(date.getTime())) element.textContent = relativeLabel(date);
    });
  }

  updateRelativeTimes();
  window.setInterval(updateRelativeTimes, 60000);
})();
