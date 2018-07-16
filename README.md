# USATT Statistics

**Disclaimer: this is a project I did in my spare time and I don't guarantee absolute accuracy/validity of data. There are currently 
no test suites.**

I web-scraped the USATT website to determine head-to-head statistics from a multitude of locations (countries and US states).
As of now, this data comprises stats from **6980** officially-sanctioned tournaments, **1925481** matches, and **56971** players. 

Locations include these state/country abbreviations: **'AA', 'AB', 'AE', 'AH', 'AI', 'AK', 'AL', 'AM', 'AN', 'AO', 'AP', 'AR', 'AZ', 'BA', 'BC', 'BL', 'BN', 'BR', 'BU', 'CA', 'CH', 'CN', 'CO', 'CT', 'DC', 'DE', 'DK', 'DO', 'DQ', 'FI', 'FL', 'FN', 'FR', 'FU', 'GA', 'GE', 'HI', 'HU', 'IA', 'ID', 'IL', 'IN', 'JK', 'JM', 'JO', 'JP', 'KR', 'KS', 'KY', 'LA', 'MA', 'MB', 'MD', 'ME', 'MI', 'MN', 'MO', 'MS', 'MT', 'NB', 'NC', 'ND', 'NE', 'NG', 'NH', 'NJ', 'NM', 'NP', 'NV', 'NY', 'OH', 'OK', 'ON', 'OR', 'PA', 'PB', 'PE', 'PH', 'PK', 'PL', 'PR', 'QC', 'RI', 'RO', 'RU', 'SC', 'SD', 'SE', 'SH', 'SK', 'TN', 'TP', 'TT', 'TX', 'UG', 'US', 'UT', 'VA', 'VE', 'VT', 'WA', 'WI', 'WV', 'WY', 'ABW', 'ANT', 'ARM', 'AUS', 'BEL', 'BMU', 'BRA', 'BRB', 'CAN', 'CHE', 'CHL', 'COL', 'DEU', 'ECU', 'FRA', 'GBR', 'GRC', 'GTM', 'GUY', 'HKG', 'HRV', 'IND', 'IRL', 'ISR', 'JAM', 'JPN', 'KAZ', 'KOR', 'MEX', 'N/A', 'NPL', 'PAK', 'PAN', 'PER', 'PRI', 'ROU', 'RUS', 'SLV', 'SVN', 'SWE', 'THA', 'TWN', 'TZA', 'USA', 'VEN', 'VNM', ' OTHER'**
wherein incorrectly-inputted locations or locations which don't fall within the 2 to 3 abbreviation constraint will fall into the ' OTHER' category.

The statistics can be found in the `tt_statics.xlsx` file, and the measures I was looking for were average loss rating difference, average
win rating difference, median loss rating difference, meadian win rating difference, number of losses, number of wins, and win/lose ratio.
I opted to use a `.xlsx` file so that anyone can easily view the data.

### Explanations:

Within the `tt_statistics.xlsx` file, you might see something like this:

```
avg_loss_rating_diff				
				
	AB	AE	AK	AL
AB	N/A	N/A	N/A	N/A
AK	-12	773	347	N/A
AL	N/A	N/A	650	471
AR	N/A	N/A	N/A	683
AZ	N/A	N/A	274	N/A
CA	165	N/A	364	776
```

For example, this means that within this given rating interval, players from **AK** (Alaska) on average lose to players from **AB**
with ratings 12 points lower than **AK** ratings. **AK** players on average lose to players from **AE** who are rated 773 points
higher. **AK** players on average lose to players from fellow **AK** players who are rated 347 points higher. When looking at 
**AK** and **AL**'s intersection, the 'N/A' means there is not any data (e.g. for this rating interval, **AK** players have never
played against **AL** players or there is only win data instead of loss data).

Here's another example for avg_win_rating_diff:
```
avg_win_rating_diff			
			
	AB	AE	AK
AB	N/A	N/A	N/A
AK	158	N/A	-186
AL	N/A	N/A	N/A
```

In this case, players from **AK** on average beat players from **AB** who are rated 158 points higher, but **AK** players on average
win against fellow **AK** players who are rated 186 points lower. This could be due to the fact that there is a larger sample size for **AK**
vs **AK** players because there may be more local tournaments.

### Cached Data and Data Structures

In order to speed up subsequent script runs, I've opted to cache relevant data within the `/pickle` folder. Pickle is the python library I
used to serialize and de-serialize Python objects. The following `.pkl` files are named by function, and the files are in the order that
they're used within the script:

* `.parse_us_cities_states_csv.pkl`: a file which represents city-state mappings gathered from the `us_cities_states_counties.csv` file. 

    ```
    {
      ...
      'Abilene Christian Univ': 'TX',
      'Abingdon': 'IL',
      'Abington': 'IN',
      'Abiquiu': 'NM',
      ...
    }
    ```
  
* `.get_preliminary_dicts.pkl`: a file which contains 
  * a dictionary mapping respective player IDs to their location and rating. Note that player IDs are **not** USATT IDs but rather 
  are the primary key designations the USATT website separately uses to uniquely keep track of players.
  
    ```
    {
       ...
       4: ('LA', 1821),
       5: ('IL', 284),
       6: ('NY', 402),
       7: ('IL', 1576),
       8: ('PA', 1497),
       9: ('IN', 1145),
       ...
     }
    ```
  
  * a dictionary mapping rating intervals to dictionaries of locations mapping to empty win dictionaries and loss dictionaries.
  
    ```
    {
      '0:250': {  
        ...
        'AA': {'L': {}, 'W': {}},
        'AB': {'L': {}, 'W': {}},
        'AH': {'L': {}, 'W': {}},
        'AK': {'L': {}, 'W': {}},
        ...
      },
      '250:500': {  
        ...
        'AA': {'L': {}, 'W': {}},
        'AB': {'L': {}, 'W': {}},
        'AH': {'L': {}, 'W': {}},
        'AK': {'L': {}, 'W': {}},
        ...
      },
      ...
    }
    ```
  
* `.get_main_info.pkl`: a file which includes un-aggregated tournament data. This is important because this is the main function which
takes a few hours to run in order to scrape all of the tournament data. Additional web-scraping isn't necessary unless you want to have
completely up-to-date information.

  ```
    {'0:250': {' OTHER': {'L': {'N/A': [749, 901, 902],
                              'NJ': [489, 319, 275, 839, 1609, 1634, 897, 319],
                              'NY': [662, 86, 198, 540, 383, 660],
                              'PA': [-6]},
                        'W': {'AL': [267],
                              'CA': [396],
                              'KS': [-79],
                              'PA': [689]}},
               'AA': {'L': {}, 'W': {}},
               'AB': {'L': {}, 'W': {}},
               'AH': {'L': {}, 'W': {}},
               'AK': {'L': {}, 'W': {}},
               'AL': {'L': {'AL': [1223, 1198, 641],
                            'CA': [811, 1273, 1425, 1514, 2272, 649, 1784],
                            'IN': [1300],
                            'MO': [1147],
                            'NJ': [443],
                            'TX': [1101]},
                      'W': {}},
               'AP': {'L': {}, 'W': {}},
               'AR': {'L': {'AR': [1403]},
               ...
              }
              ...
    }
                
  ```

### Next Steps

Statistical analysis of data.. somehow
