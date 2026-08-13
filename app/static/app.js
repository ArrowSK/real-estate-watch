(() => {
  const canvases = [...document.querySelectorAll('canvas[data-market-chart], #marketChart')];
  if (!canvases.length) return;

  const parseSeries = canvas => {
    try { return JSON.parse(canvas.dataset.series || '[]'); } catch (_) { return []; }
  };

  const draw = canvas => {
    const series = parseSeries(canvas);
    if (!series.length) return;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 700;
    const height = canvas.clientHeight || 300;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const pad = {left: 62, right: 18, top: 20, bottom: 42};
    const plotW = Math.max(width - pad.left - pad.right, 1);
    const plotH = Math.max(height - pad.top - pad.bottom, 1);
    const values = series.map(x => Number(x.price)).filter(Number.isFinite);
    if (!values.length) return;
    let min = Math.min(...values), max = Math.max(...values);
    const spread = Math.max(max - min, max * 0.08, 1);
    min -= spread * 0.12; max += spread * 0.12;

    const css = getComputedStyle(document.documentElement);
    const text = css.getPropertyValue('--muted').trim() || '#65716c';
    const line = css.getPropertyValue('--rule').trim() || '#cfc5b5';
    const accent = css.getPropertyValue('--signal').trim() || '#c96545';
    const teal = css.getPropertyValue('--teal').trim() || '#296966';
    const graph = canvas.dataset.tone === 'official' ? teal : accent;

    ctx.font = '11px ui-monospace, monospace';
    ctx.fillStyle = text; ctx.strokeStyle = line; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + plotH * i / 4;
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
      const value = max - (max - min) * i / 4;
      ctx.textAlign = 'left'; ctx.fillText(`${Math.round(value / 1000)}k`, 7, y + 4);
    }

    const xAt = i => pad.left + (series.length === 1 ? plotW / 2 : plotW * i / (series.length - 1));
    const yAt = v => pad.top + plotH - (v - min) / (max - min) * plotH;
    ctx.strokeStyle = graph; ctx.lineWidth = 2.5; ctx.beginPath();
    series.forEach((item, i) => {
      const x = xAt(i), y = yAt(Number(item.price));
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    series.forEach((item, i) => {
      const x = xAt(i), y = yAt(Number(item.price));
      ctx.fillStyle = graph; ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2); ctx.fill();
      if (series.length <= 7 || i === 0 || i === series.length - 1 || i % Math.ceil(series.length / 5) === 0) {
        ctx.fillStyle = text;
        ctx.textAlign = i === 0 ? 'left' : i === series.length - 1 ? 'right' : 'center';
        ctx.fillText(item.period, x, height - 14);
      }
    });
  };

  const redraw = () => canvases.forEach(draw);
  redraw();
  let resizeFrame;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(redraw);
  });
})();
