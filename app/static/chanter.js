let quotes = ["Power over patents is power over all.", 
    "Andrew Blattman commands it. It is done.", 
    "Indefiniteness is the mind-killer.", 
    "The people who can patent a thing, they control it.",
    "The mystery of patent eligibility isn't a problem to solve, but a reality to experience.",
    "No more terrible disaster could befall your people than for them to fall into the hands of a litigator.",
    "Patent prosecution teaches the attitude of the knife."];

function getDailyIndex() {
    let today = new Date();
    return today.getDate() % quotes.length;
}

function getData() {
    let data_url = "/api/registrations?filter=pat"
    fetch(data_url)
    .then(response => response.json())
    .then(data => {
      startChant(data);
    })
}

function startChant(attorneys) {
    console.log(attorneys);
    // Hide the button while chanting
    const button = document.getElementById("Button container");
    button.style.display = "none";
    let lines = [];

    //  Random quote if there's no new attorneys
    if (attorneys.length === 0) {
        lines.push(quotes[getDailyIndex(quotes.length)]);
        startAudio("growl");
    } else {
        for (let i = 0; i < attorneys.length; i++) {
            lines.push(attorneys[i].Name + " of " + attorneys[i].Firm + ".");
        }
        startAudio("chant");
    }
    
    // Set up text fading
    const fading_text = document.getElementById("Display text");
    let faded_in = false;
    let opacity = 0;
    let timestamp = performance.now();
    // Constants for timing adjustment
    const TIME_BEFORE_FADEIN = 1300;
    const TIME_BEFORE_FADEOUT = 4300;
    const FADE_RATE =  0.03;

    const intervalID = setInterval(fadeText, 16);
    let counter = 0;
    fading_text.innerHTML = lines[0];
    
    function fadeText() {
        let elapsedTime = performance.now() - timestamp;

        if (!faded_in & (elapsedTime >= TIME_BEFORE_FADEIN)) {
            opacity = Math.min(opacity + FADE_RATE, 1);
            if (opacity === 1) {
                faded_in = true;
                timestamp = performance.now();
            }
        } else if (faded_in & (elapsedTime >= TIME_BEFORE_FADEOUT)) {
            opacity = Math.max(opacity - FADE_RATE, 0);
            if (opacity === 0) {
                faded_in = false;
                timestamp = performance.now();
                nextLine();
            }
        }
        fading_text.style.opacity = opacity;
    }

    function nextLine() {
        counter++;
        if(counter >= lines.length) {
            fading_text.innerHTML = "";
            clearInterval(intervalID);
        } else {
            fading_text.innerHTML = lines[counter];
        }
    }

    function startAudio(id) {
        let audio = document.getElementById(id);
        audio.play();
        audio.addEventListener('ended', atAudioEnd);
    }
    
    function atAudioEnd(evt) {
        // Restart audio if text is still cycling, otherwise show the button
        if (counter < lines.length) {
            evt.currentTarget.play();
        } else {
            button.style.display = "block";
        }
    }
}