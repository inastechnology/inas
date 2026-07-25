const slides = [...document.querySelectorAll('.slide')];
const currentLabel = document.querySelector('[data-current]');
const totalLabel = document.querySelector('[data-total]');
let currentIndex = 0;

totalLabel.textContent = String(slides.length);

function updateCurrent(index, updateHash = false) {
  currentIndex = Math.max(0, Math.min(index, slides.length - 1));
  currentLabel.textContent = String(currentIndex + 1);
  document.title = `${String(currentIndex + 1).padStart(2, '0')} — ${slides[currentIndex].dataset.title} | INAS Pitch`;
  if (updateHash) history.replaceState(null, '', `#slide-${currentIndex + 1}`);
}

function goTo(index) {
  const nextIndex = Math.max(0, Math.min(index, slides.length - 1));
  slides[nextIndex].scrollIntoView({ behavior: 'smooth', block: 'start' });
  updateCurrent(nextIndex, true);
}

document.querySelector('[data-prev]').addEventListener('click', () => goTo(currentIndex - 1));
document.querySelector('[data-next]').addEventListener('click', () => goTo(currentIndex + 1));
document.querySelector('[data-fullscreen]').addEventListener('click', async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await document.documentElement.requestFullscreen();
});

document.addEventListener('keydown', (event) => {
  if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(event.key)) {
    event.preventDefault();
    goTo(currentIndex + 1);
  }
  if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key)) {
    event.preventDefault();
    goTo(currentIndex - 1);
  }
  if (event.key === 'Home') {
    event.preventDefault();
    goTo(0);
  }
  if (event.key === 'End') {
    event.preventDefault();
    goTo(slides.length - 1);
  }
});

const observer = new IntersectionObserver((entries) => {
  const visible = entries
    .filter((entry) => entry.isIntersecting)
    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (!visible) return;
  updateCurrent(slides.indexOf(visible.target), false);
}, { threshold: [.45, .7, .9] });

slides.forEach((slide) => observer.observe(slide));

const requested = Number.parseInt(location.hash.replace('#slide-', ''), 10);
if (Number.isInteger(requested) && requested >= 1 && requested <= slides.length) {
  requestAnimationFrame(() => goTo(requested - 1));
} else {
  updateCurrent(0, false);
}
