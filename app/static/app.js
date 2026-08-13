(() => {
  const canvas = document.getElementById('marketChart');
  if (!canvas) return;
  let series = [];
  try { series = JSON.parse(canvas.dataset.series || '[]'); } catch (_) { return; }
  if (!series.length) return;

  const draw = () => {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 700;
    const height = canvas.clientHeight || 300;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext('2d');
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);

    const pad = {left: 58, right: 18, top: 18, bottom: 42};
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    const values = series.map(x => Number(x.price));
    let min = Math.min(...values);
    let max = Math.max(...values);
    const spread = Math.max(max - min, max * 0.08, 1);
    min -= spread * 0.12;
    max += spread * 0.12;

    const css = getComputedStyle(document.documentElement);
    const text = css.getPropertyValue('--muted').trim() || '#66727f';
    const line = css.getPropertyValue('--line').trim() || '#dce2e8';
    const accent = css.getPropertyValue('--accent').trim() || '#183b56';
    ctx.font = '12px system-ui, sans-serif';
    ctx.fillStyle = text;
    ctx.strokeStyle = line;
    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (plotH * i / 4);
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
      const value = max - (max - min) * i / 4;
      ctx.fillText(`${Math.round(value / 1000)}k`, 8, y + 4);
    }

    const xAt = i => pad.left + (series.length === 1 ? plotW / 2 : plotW * i / (series.length - 1));
    const yAt = v => pad.top + plotH - (v - min) / (max - min) * plotH;

    ctx.strokeStyle = accent;
    ctx.lineWidth = 3;
    ctx.beginPath();
    series.forEach((item, i) => {
      const x = xAt(i), y = yAt(Number(item.price));
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    ctx.fillStyle = accent;
    series.forEach((item, i) => {
      const x = xAt(i), y = yAt(Number(item.price));
      ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
      if (series.length <= 6 || i === 0 || i === series.length - 1 || i % 2 === 0) {
        ctx.fillStyle = text;
        ctx.textAlign = i === 0 ? 'left' : i === series.length - 1 ? 'right' : 'center';
        ctx.fillText(item.period, x, height - 14);
        ctx.fillStyle = accent;
      }
    });
  };

  draw();
  window.addEventListener('resize', () => window.requestAnimationFrame(draw));
})();
