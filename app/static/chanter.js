const quotes = [
  "Power over patents is power over all.",
  "Andrew Blattman commands it. It is done.",
  "Indefiniteness is the mind-killer.",
  "The people who can patent a thing, they control it.",
  "The mystery of patent eligibility isn't a problem to solve, but a reality to experience.",
  "No more terrible disaster could befall your people than for them to fall into the hands of a litigator.",
  "Patent prosecution teaches the attitude of the knife.",
];

function getDailyIndex() {
  return new Date().getDate() % quotes.length;
}

async function getData() {
  const startButton = document.getElementById("start-button");
  if (startButton) startButton.disabled = true;

  try {
    // The ritual has one job: present new registrations.  Date ranges,
    // ordering and the other register views belong on the main directory.
    const response = await fetch("/api/registrations?per_page=100");
    if (!response.ok) throw new Error(`Register request failed (${response.status})`);
    const data = await response.json();
    startChant(data);
  } catch (error) {
    console.error(error);
    if (startButton) startButton.disabled = false;
  }
}

function startChant(data) {
  const attorneys = Array.isArray(data.items) ? data.items : [];
  const display = document.getElementById("display-text");
  const controls = document.getElementById("button-container");
  const startButton = document.getElementById("start-button");
  const chant = document.getElementById("chant");
  const growl = document.getElementById("growl");

  if (!display || !controls || !startButton) return;

  const lines = attorneys.length
    ? attorneys.map((attorney) => {
        const firm = attorney.firm ? ` of House ${attorney.firm}.` : ".";
        return `${attorney.name}${firm}`;
      })
    : [quotes[getDailyIndex()]];

  controls.classList.add("is-hidden");
  display.classList.add("is-active");

  let audioFinished = false;
  let linesFinished = false;
  let lineIndex = 0;
  let lineTimer;

  const finishIfReady = () => {
    if (!audioFinished || !linesFinished) return;
    display.classList.remove("is-active");
    controls.classList.remove("is-hidden");
    startButton.disabled = false;
  };

  const finishAudio = () => {
    audioFinished = true;
    finishIfReady();
  };

  const playAudio = (audio) => {
    if (!audio) {
      finishAudio();
      return;
    }
    audio.currentTime = 0;
    audio.addEventListener("ended", finishAudio, { once: true });
    audio.addEventListener("error", finishAudio, { once: true });
    const playback = audio.play();
    if (playback && typeof playback.catch === "function") {
      playback.catch(finishAudio);
    }
  };

  const showLine = () => {
    display.classList.remove("is-line-visible");
    display.textContent = lines[lineIndex];
    // Allow the opacity transition to start from zero for each line.
    window.requestAnimationFrame(() => display.classList.add("is-line-visible"));

    lineTimer = window.setTimeout(() => {
      display.classList.remove("is-line-visible");
      window.setTimeout(() => {
        lineIndex += 1;
        if (lineIndex >= lines.length) {
          linesFinished = true;
          finishIfReady();
        } else {
          showLine();
        }
      }, 850);
    }, 4300);
  };

  // The growl is used for a quiet register update; otherwise use the chant.
  playAudio(attorneys.length ? chant : growl);
  showLine();

  // A damaged audio file should never leave the ritual controls hidden.
  window.setTimeout(() => {
    if (!audioFinished) finishAudio();
  }, Math.max(7000, lines.length * 5200));
}

document.addEventListener("DOMContentLoaded", () => {
  const startButton = document.getElementById("start-button");
  if (startButton) startButton.addEventListener("click", getData);
});
