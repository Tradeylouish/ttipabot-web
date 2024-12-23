const text = ["Louis Francisco Yates Habberfield-Short of Xero.", "James Barrett of AJ Park.", "Evelyn Body of Xero.", "David Simunic of AJ Park."];
let counter = 0;

function startChant() {
    const fading_name =  document.getElementById("Attorney name");
    fading_name.innerHTML = text[0];
    var faded_in = false;

    const button = document.getElementById("start_button");
    button.style.display = "none";
    playAudio();

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

function playAudio() {
    var audio = document.getElementById("chant");
    audio.play();
}

function pauseAudio() {
    var audio = document.getElementById("chant");
    audio.pause();
}