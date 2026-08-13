(() => {
  const canvas = document.getElementById('marketChart');
  if (!canvas) return;

  const parse = value => {
    try { return JSON.parse(value || '[]'); } catch (_) { return []; }
  };
  const official = parse(canvas.dataset.official);
  const asking = parse(canvas.dataset.asking);
  const all = [...official, ...asking];
  if (!all.length) return;

  const timeOf = item => {
    const raw = item.date || item.period;
    const parsed = Date.parse(raw);
    if (Number.isFinite(parsed)) return parsed;
    const quarter = String(raw || '').match(/^(\d{4})-Q([1-4])$/);
    if (quarter) return Date.UTC(Number(quarter[1]), Number(quarter[2]) * 3 - 1, 1);
    return 0;
  };

  const draw = () => {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 700;
    const height = canvas.clientHeight || 320;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const pad = {left: width < 520 ? 48 : 66, right: 18, top: 18, bottom: 42};
    const plotW = Math.max(width - pad.left - pad.right, 1);
    const plotH = Math.max(height - pad.top - pad.bottom, 1);
    const values = all.map(item => Number(item.price)).filter(Number.isFinite);
    if (!values.length) return;
    let min = Math.min(...values);
    let max = Math.max(...values);
    const spread = Math.max(max - min, max * 0.08, 1);
    min -= spread * 0.12;
    max += spread * 0.12;

    let times = all.map(timeOf).filter(value => value > 0);
    let minTime = times.length ? Math.min(...times) : 0;
    let maxTime = times.length ? Math.max(...times) : 1;
    if (minTime === maxTime) maxTime = minTime + 86400000;

    const css = getComputedStyle(document.documentElement);
    const text = css.getPropertyValue('--muted').trim();
    const grid = css.getPropertyValue('--line').trim();
    const tx = css.getPropertyValue('--transaction').trim();
    const ask = css.getPropertyValue('--asking').trim();
    const panel = css.getPropertyValue('--panel').trim();

    const xAt = item => pad.left + ((timeOf(item) - minTime) / (maxTime - minTime)) * plotW;
    const yAt = value => pad.top + plotH - ((value - min) / (max - min)) * plotH;

    ctx.font = '11px ui-monospace, SFMono-Regular, Consolas, monospace';
    ctx.fillStyle = text;
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    ctx.textAlign = 'left';

    for (let i = 0; i <= 4; i++) {
      const y = pad.top + plotH * i / 4;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(width - pad.right, y);
      ctx.stroke();
      const value = max - (max - min) * i / 4;
      ctx.fillText(`${Math.round(value / 1000)}k`, 6, y + 4);
    }

    const ticks = width < 620 ? 3 : 5;
    for (let i = 0; i < ticks; i++) {
      const fraction = ticks === 1 ? 0 : i / (ticks - 1);
      const when = minTime + (maxTime - minTime) * fraction;
      const x = pad.left + plotW * fraction;
      const date = new Date(when);
      const label = Number.isFinite(date.getTime())
        ? `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
        : '';
      ctx.fillStyle = text;
      ctx.textAlign = i === 0 ? 'left' : (i === ticks - 1 ? 'right' : 'center');
      ctx.fillText(label, x, height - 13);
    }

    const drawSeries = (series, color, dashed, points) => {
      const valid = [...series]
        .filter(item => Number.isFinite(Number(item.price)) && timeOf(item) > 0)
        .sort((a, b) => timeOf(a) - timeOf(b));
      if (!valid.length) return;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = dashed ? 2.2 : 3;
      ctx.setLineDash(dashed ? [7, 5] : []);
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.beginPath();
      valid.forEach((item, index) => {
        const x = xAt(item);
        const y = yAt(Number(item.price));
        if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.restore();

      if (points) {
        valid.forEach(item => {
          const x = xAt(item);
          const y = yAt(Number(item.price));
          ctx.beginPath();
          ctx.arc(x, y, 3.3, 0, Math.PI * 2);
          ctx.fillStyle = panel;
          ctx.fill();
          ctx.lineWidth = 2;
          ctx.strokeStyle = color;
          ctx.stroke();
        });
      }
    };

    drawSeries(official, tx, false, true);
    drawSeries(asking, ask, true, asking.length <= 35);
  };

  draw();
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => window.requestAnimationFrame(draw), 80);
  });
})();
