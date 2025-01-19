# TTIPABot Web

This is a Flask app which serves APIs to the [TTIPABot tool](https://github.com/Tradeylouish/ttipabot). It also serves a frontend that uses the registrations API to congratulate new patent attorneys with ritual chanting. The app is hosted at [ttipabot.com](https://ttipabot.com). The server scrapes the register at 7pm NZT daily. 

The currently available API endpoints are: 

[ttipabot.com/api/registrations](https://ttipabot.com/api/registrations): This returns any newly registered patent attorneys in the last update to the register.

[ttipabot.com/api/movements](https://ttipabot.com/api/movements): This returns any IP attorneys that changed firms in the last update to the register.

[ttipabot.com/api/lapses](https://ttipabot.com/api/lapses): This returns any IP attorneys whose registration lapsed in the last update to the register.

[ttipabot.com/api/names](https://ttipabot.com/api/names): This returns the IP attorneys with the top 10 longest names on the register.

Support for paramaters in API queries is under development.
