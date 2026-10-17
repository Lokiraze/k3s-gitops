class MediaPosterGrid extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }
  setConfig(config) {
    if (!config.entity) throw new Error('A media sensor is required');
    this.config = config;
    this.lastState = undefined;
    if (this._hass) this.hass = this._hass;
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.config) return;
    const state = hass.states[this.config.entity];
    if (state && state === this.lastState) return;
    this.lastState = state;
    let data = state?.attributes.data ?? [];
    try { if (typeof data === 'string') data = JSON.parse(data); } catch { data = []; }
    const items = Array.isArray(data) ? data.filter(item => item && item.title && item.airdate).slice(0, this.config.max ?? 12) : [];
    this.shadowRoot.innerHTML = `<style>
      :host { display:block; }
      ha-card { background:transparent; border:0; box-shadow:none; padding:20px 24px 28px; box-sizing:border-box; max-width:1280px; margin:0 auto; }
      header { display:flex; align-items:baseline; gap:12px; margin:0 0 20px; }
      h2 { font-size:22px; font-weight:600; letter-spacing:-.4px; margin:0; color:var(--primary-text-color); }
      .count,.date,.empty { color:var(--secondary-text-color); font-size:13px; }
      .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(145px,1fr)); gap:26px 20px; }
      article { min-width:0; }
      .art { aspect-ratio:2/3; overflow:hidden; border-radius:12px; background:var(--secondary-background-color); position:relative; box-shadow:0 6px 18px #0003; }
      img { width:100%; height:100%; object-fit:cover; display:block; transition:transform .2s; }
      article:hover img { transform:scale(1.025); }
      .fallback { display:none; position:absolute; inset:0; align-items:center; justify-content:center; padding:16px; text-align:center; color:var(--secondary-text-color); }
      h3 { font-size:15px; line-height:1.35; font-weight:600; margin:12px 0 5px; color:var(--primary-text-color); overflow-wrap:anywhere; }
      .episode { font-size:12px; color:var(--secondary-text-color); margin-top:5px; line-height:1.4; }
      @media(max-width:480px) { .grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:22px 14px; } }
      @media(prefers-reduced-motion:reduce) { img { transition:none; } }
    </style><ha-card><header><h2></h2><span class="count"></span></header><div class="grid"></div></ha-card>`;
    this.shadowRoot.querySelector('h2').textContent = this.config.title ?? 'Upcoming';
    this.shadowRoot.querySelector('.count').textContent = `${items.length} ${items.length === 1 ? 'release' : 'releases'}`;
    const grid = this.shadowRoot.querySelector('.grid');
    if (!items.length) {
      const empty = document.createElement('p'); empty.className = 'empty';
      empty.textContent = !state || ['unavailable','unknown'].includes(state.state) ? 'Media information is unavailable.' : 'No upcoming releases in this period.';
      grid.append(empty);
    }
    for (const item of items) {
      const article = document.createElement('article');
      const art = document.createElement('div'); art.className = 'art';
      const fallback = document.createElement('div'); fallback.className = 'fallback'; fallback.textContent = item.title;
      const img = document.createElement('img'); img.alt = `${item.title} poster`; img.loading = 'lazy';
      img.addEventListener('error', () => { img.hidden = true; img.style.display = 'none'; fallback.style.display = 'flex'; });
      try { const url = new URL(item.poster); if (!['https:', 'http:'].includes(url.protocol)) throw new Error(); img.src = url.href; }
      catch { img.style.display = 'none'; fallback.style.display = 'flex'; }
      art.append(img,fallback);
      const title = document.createElement('h3'); title.textContent = item.title;
      const date = document.createElement('div'); date.className = 'date';
      const when = new Date(item.airdate);
      date.textContent = Number.isNaN(when.getTime()) ? 'Date to be announced' : when.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
      article.append(art,title,date);
      if (item.number || item.episode) {
        const episode = document.createElement('div'); episode.className = 'episode';
        episode.textContent = [item.number,item.episode].filter(Boolean).join(' · '); article.append(episode);
      }
      grid.append(article);
    }
  }
  getCardSize() { return 6; }
}
if (!customElements.get('media-poster-grid')) customElements.define('media-poster-grid', MediaPosterGrid);
