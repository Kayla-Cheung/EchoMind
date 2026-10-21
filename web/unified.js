/* Switches experiment panels without navigation or merging datasets. */
(() => {
  'use strict';
  const names = ['history', 'mechanism', 'ablation', 'prompts'];
  const tabs = Object.fromEntries(names.map(n => [n, document.getElementById('tab-' + n)]));
  const views = Object.fromEntries(names.map(n => [n, document.getElementById('view-' + n)]));
  function show(name, saveHash) {
    if (!tabs[name]) name = 'history';
    for (const key of Object.keys(tabs)) {
      const selected = key === name;
      tabs[key].setAttribute('aria-selected', String(selected));
      tabs[key].tabIndex = selected ? 0 : -1;
      views[key].hidden = !selected;
    }
    if (saveHash && window.location.hash !== '#' + name) window.location.hash = name;
  }
  show(window.location.hash.slice(1) || (window.location.pathname === '/ablation' ? 'ablation' : 'history'), false);
  for (const name of Object.keys(tabs)) {
    tabs[name].addEventListener('click', () => show(name, true));
    tabs[name].addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? names[0] : event.key === 'End' ? names.at(-1) : names[(names.indexOf(name) + (event.key === 'ArrowRight' ? 1 : names.length - 1)) % names.length];
      show(next, true); tabs[next].focus();
    });
  }
  window.addEventListener('hashchange', () => show(window.location.hash.slice(1), false));
})();
