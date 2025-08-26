# TTIPABot Web

This is a Flask app which evolved from the [TTIPABot tool](https://github.com/Tradeylouish/ttipabot) and provides most of the same functions. It also serves a frontend that uses backend APIs to perform ritual chanting, including for newly registered patent attorneys. The app is hosted at [ttipabot.com](https://ttipabot.com). The server scrapes the register at 7pm NZT daily. 

The currently available API endpoints are: 

[ttipabot.com/api/registrations](https://ttipabot.com/api/registrations): This returns any newly registered patent attorneys between two dates (defaults to the last week).

[ttipabot.com/api/movements](https://ttipabot.com/api/movements): This returns any IP attorneys that changed firms between two dates (defaults to the last week).

[ttipabot.com/api/lapses](https://ttipabot.com/api/lapses): This returns any IP attorneys whose registration lapsed between two dates (defaults to the last week).

[ttipabot.com/api/attorneys](https://ttipabot.com/api/attorneys): This returns a collection of IP attorneys and supports a few different orderings, including name length using the query parameter ?OrderBy=name_length

APIs are in the process of being tidied up and full documentation is to come, including for the firms endpoint which requires some data cleanup to get working.