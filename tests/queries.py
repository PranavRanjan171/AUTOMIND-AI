"""Shared list of realistic searches used by the tests."""
QUERIES = [
    # the three problems reported on the first version
    "most expensive car", "luxury car", "BMW", "Mercedes SUV", "Audi under 60 lakh", "luxury sedan under 1 crore",
    "cheapest car", "fastest car", "best mileage car", "lowest maintenance car", "most expensive SUV under 2 crore",
    "ferrari", "lamborghini", "rolls royce", "porsche 911", "Land Rover Defender", "Volvo", "Lexus hybrid",
    # everyday searches
    "7 seater under 20 lakh", "7 seater automatic under 25 lakh", "SUV under 20 lakh with good mileage", "petrol car with low maintenance",
    "fast car under 30 lakh", "electric car under 20 lakh", "cheapest electric car", "diesel automatic suv under 25 lakh",
    "family car with good mileage under 12 lakh", "automatic petrol under 8 lakh", "first car for a student", "city traffic automatic",
    "something comfortable for long drives", "CNG car with 25 kmpl", "hybrid", "2 seater sports car", "sports car under 1 crore",
    "like a Creta but automatic", "Verna", "Honda City", "similar to Innova", "cheap car under 6 lakh", "suv", "automatic", "electric car",
    # typos, hinglish, negations, ranges
    "luxry sedn under 80 lakh", "mercedez suv", "suvv petrl automtic under 15 lakh", "sasti gaadi", "no diesel suv under 20 lakh",
    "7 seater diesel no mahindra", "avoid tata hatchback under 10 lakh", "between 10 and 15 lakh sedan", "around 12 lakh suv",
    "above 1.5 crore", "5000000 budget", "1,00,00,000 luxury", "audi or bmw under 60 lakh", "toyota 7 seater", "kia electric",
    "latest model suv under 20 lakh", "2024 model petrol under 15 lakh", "premium suv", "money is no issue", "jeep wrangler",
    "mini cooper", "BYD electric", "eco friendly car", "taxi car under 10 lakh", "off road adventure car", "big family joint family car",
    "mileage above 22 kmpl", "most fuel efficient petrol car", "biggest car", "most powerful electric car", "cheapest luxury car",
    "best car under 10 lakh", "6 seater under 30 lakh", "hatchback with sunroof", "xyz", "a",
    # unusual / indirect descriptions
    "I need a car to carry my 2 kids, grandparents and a dog", "something like a mini tank for bad village roads",
    "car for a rich businessman who wants to impress clients", "i want to go zero petrol expenses", "budget 15L max, 6 people, no clutch pedal",
    "fastest thing under 50 lakh", "car with 30+ kmpl", "i dont want a suv, i dont want diesel, 10 to 14 lakh", "luxurious electric sedan",
    "cheapest 7 seater", "the priciest hybrid", "gaadi chahiye 5 seater, automatic, 8 lakh tak", "batmobile", "I'm 6'5 tall and need space, under 25 lakh",
    "ola uber taxi car under 10 lakh", "gift for my wife, small automatic, under 9 lakh", "i hate manual gearbox and hate petrol", "cheap CNG hatchback",
    "top of the line german luxury", "best electric suv money can buy", "family weekend trips to the hills", "Maruti ya Hyundai, 10 lakh ke andar, mileage achha",
    "compact car for tight parking in mumbai, no more than 7 lakh", "korean suv under 15 lakh", "british luxury suv", "italian supercar", "japanese hybrid",
    # subjective requests the data cannot answer directly
    "long drive with good sound system", "ladies type car", "pink car", "good rated car", "particular colour", "big tyres", "stylish",
    "stylish suv under 20 lakh with good sound system", "sedn", "good car",
]

QUERIES += [
    # reported bugs: negated lists, two superlatives, "billionaire", elderly / nervous drivers, real off-roaders, taxis
    "I don't want Tata or Mahindra, petrol SUV around 12 lakh", "no diesel or CNG hatchback", "avoid tata and mahindra and maruti", "don't want manual or diesel",
    "no diesel, automatic", "not interested in maruti or hyundai", "other than toyota, 7 seater", "no german cars under 1 crore",
    "Most spacious car with lowest maintenance", "fastest and cheapest car", "most fuel efficient and cheapest to maintain",
    "Billionaire level car, money is no issue", "ultra luxury suv", "money is no issue, sedan", "cost no object 7 seater",
    "My parents are old, easy to enter car", "senior citizens, knee pain", "my wife is scared of driving, no gear", "nervous new driver, automatic under 10 lakh",
    "off-road in the mountains", "4x4 for rough terrain", "off-road under 15 lakh", "rugged jungle safari car", "off road money no issue",
    "Taxi for Ola/Uber", "taxi under 10 lakh", "cab for fleet, CNG", "uber car suv",
]

# multi-step conversations: each later message refines the previous search
CHAINS = [
    ["7 seater under 20 lakh", "cheaper", "only automatic", "no diesel", "bigger", "more expensive"],
    ["suv under 15 lakh", "diesel", "actually petrol", "remove budget"],
    ["luxury sedan under 1 crore", "cheaper", "more mileage", "electric"],
    ["most expensive car", "cheaper"],
    ["hatchback", "under 6 lakh", "automatic", "more powerful", "smaller"],
    ["family car", "toyota", "increase budget"],
    ["electric car under 25 lakh", "bmw", "start over"],
    ["car with 22 kmpl", "more mileage", "only maruti"],
    ["Most spacious car with lowest maintenance", "only automatic", "cheaper"],
    ["off-road in the mountains", "under 15 lakh", "no mahindra"],
]
