let counter = 0;

let quotes = ["Power over patents is power over all.", "Andrew Blattman commands it. It is done.", "Indefiniteness is the mind-killer.", "The people who can patent a thing, they control it."];

//# Constants for timing adjustment, based on Dune movie intro
// WAIT_TIME = 1500
// FADEOUT_TIME = 6000

function getRandomInt(max) {
    return Math.floor(Math.random() * max);
}

function startChant(text) {
    //  Random quote if there's no new attorneys
    if (text.length === 0) {
        text.push(quotes[getRandomInt(quotes.length)])
        playAudio("growl");
    } else {
        playAudio("chant");
    }
    console.log(text);

    // Hide the button while chanting
    const button = document.getElementById("Button container");
    button.style.display = "none";

    // Set up text fading
    const fading_name =  document.getElementById("Display text");
    fading_name.innerHTML = text[0];
    var faded_in = false;
    const intervalID = setInterval(fade, 50);
    var opacity = 0;     
    
    function fade() {

        //fading_name.innerHTML = text[counter];
        if (!faded_in) { 
            opacity = Math.min(opacity + 0.03, 1);
            if (opacity == 1) {
                faded_in = true;
            }
        } else if (faded_in) {
            opacity = Math.max(opacity - 0.03, 0);
            if (opacity == 0) {
                next_name();
                faded_in = false;
            }
        }
        fading_name.style.opacity = opacity;
    }    

    function next_name() {
        counter++;
        if(counter >= text.length) {
            counter = 0;
            fading_name.innerHTML = "";
            //pauseAudio();
            clearInterval(intervalID);
            button.style.display = "block";
        } else {
            fading_name.innerHTML = text[counter];
        }
    }
}

function playAudio(id) {
    var audio = document.getElementById(id);
    audio.play();
}

function pauseAudio(id) {
    var audio = document.getElementById(id);
    audio.pause();
}