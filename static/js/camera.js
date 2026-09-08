export function createCamera(viewport, stage, controls = {}) {
  let scale = 0.72;
  let x = 12;
  let y = 10;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  function apply() {
    stage.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
    if (controls.zoomLabel) controls.zoomLabel.textContent = `${Math.round(scale * 100)}%`;
  }
  function home() {
    const rect = viewport.getBoundingClientRect();
    const stageW = 1400;
    const stageH = 900;
    scale = clamp(Math.min((rect.width - 18) / stageW, (rect.height - 18) / stageH), 0.46, 1);
    x = (rect.width - stageW * scale) / 2;
    y = (rect.height - stageH * scale) / 2;
    apply();
  }
  function zoom(delta, anchorX = null, anchorY = null) {
    const old = scale;
    scale = clamp(scale + delta, 0.45, 1.45);
    if (anchorX !== null && anchorY !== null) {
      const rect = viewport.getBoundingClientRect();
      const ax = anchorX - rect.left;
      const ay = anchorY - rect.top;
      const worldX = (ax - x) / old;
      const worldY = (ay - y) / old;
      x = ax - worldX * scale;
      y = ay - worldY * scale;
    }
    apply();
  }

  viewport.addEventListener('pointerdown', e => {
    if (e.target.closest('button,.building-hit,.hud-drawer,input,textarea,select,label,a')) return;
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    viewport.setPointerCapture?.(e.pointerId);
    viewport.classList.add('is-dragging');
  });
  viewport.addEventListener('pointermove', e => {
    if (!dragging) return;
    x += e.clientX - lastX; y += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY; apply();
  });
  const stop = e => { dragging = false; viewport.classList.remove('is-dragging'); try { viewport.releasePointerCapture?.(e.pointerId); } catch {} };
  viewport.addEventListener('pointerup', stop);
  viewport.addEventListener('pointercancel', stop);
  viewport.addEventListener('wheel', e => {
    // Popup/drawer content owns its own scroll. Never turn those wheel
    // gestures into map zoom.
    if (e.target.closest('.hud-drawer,.hud-tasks,.building-panel,input,textarea,select')) return;
    e.preventDefault();
    zoom(e.deltaY < 0 ? 0.08 : -0.08, e.clientX, e.clientY);
  }, { passive:false });
  controls.zoomIn?.addEventListener('click', () => zoom(0.1));
  controls.zoomOut?.addEventListener('click', () => zoom(-0.1));
  controls.home?.addEventListener('click', home);
  window.addEventListener('resize', home);
  setTimeout(home, 0);
  return { home, zoom };
}
