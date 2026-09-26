# Imports
from helper_functions import get_llm_response, print_llm_response, display_table
from rich.console import Console
from rich.markdown import Markdown
import csv

f = open("itinerary.csv", "r")
csv_reader = csv.DictReader(f)
itinerary = []
for row in csv_reader:
    #print(row)
    itinerary.append(row)
f.close()

trip_stop = itinerary[1]
city = trip_stop["City"]
country = trip_stop["Country"]
arrival = trip_stop["Arrival"]
departure = trip_stop["Departure"]

prompt = f"""I will visit {city}, {country}, from {arrival} to {departure}. 
Please create a detailed daily itinerary."""

response = get_llm_response(prompt)
Console().print(Markdown(response))
