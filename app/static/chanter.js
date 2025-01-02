let quotes = ["Power over patents is power over all.", 
    "Andrew Blattman commands it. It is done.", 
    "Indefiniteness is the mind-killer.", 
    "The people who can patent a thing, they control it."];

function getRandomInt(max) {
    return Math.floor(Math.random() * max);
}

function getData() {
    let data_url = "/data"
    fetch(data_url)
    .then(response => response.json())
    .then(data => {
      startChant(data);
    })
}

function startChant(text) {
    // Hide the button while chanting
    const button = document.getElementById("Button container");
    button.style.display = "none";
    
    //  Random quote if there's no new attorneys
    if (text.length === 0) {
        text.push(quotes[getRandomInt(quotes.length)])
        startAudio("growl");
    } else {
        startAudio("chant");
    }
    console.log(text);

    // Set up text fading
    const fading_name =  document.getElementById("Display text");
    let faded_in = false;
    let opacity = 0;
    let timestamp = performance.now();
    // Constants for timing adjustment
    const TIME_BEFORE_FADEIN = 1300;
    const TIME_BEFORE_FADEOUT = 4300;
    const FADE_RATE =  0.03;

    const intervalID = setInterval(fadeText, 16);
    let counter = 0;
    fading_name.innerHTML = text[0];
    
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
                nextName();
            }
        }
        fading_name.style.opacity = opacity;
    }

    function nextName() {
        counter++;
        if(counter >= text.length) {
            fading_name.innerHTML = "";
            clearInterval(intervalID);
        } else {
            fading_name.innerHTML = text[counter];
        }
    }

    function startAudio(id) {
        let audio = document.getElementById(id);
        audio.play();
        audio.addEventListener('ended', atAudioEnd);
    }
    
    function atAudioEnd(evt) {
        // Restart audio if text is still cycling, otherwise show the button
        if (counter < text.length) {
            evt.currentTarget.play();
        } else {
            button.style.display = "block";
        }
    }
}