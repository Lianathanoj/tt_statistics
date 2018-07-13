import copy
import itertools
import numpy
import os
import pandas as pd
import pickle
import re
import requests
import string
import time
import xlsxwriter

from bs4 import BeautifulSoup
from intervaltree import IntervalTree
from pprint import pprint

NUM_INT_PLAYERS_LIMIT = 5
NUM_US_PLAYERS_LIMIT = 5
NUM_TOURNEYS_LIMIT = 3
URL = 'https://usatt.simplycompete.com'
USE_MAX = True

def cache_info(func):
    def wrapper(*args):
        cache = './pickle/{}'.format('.{}.pkl'.format(func.__name__).replace('/', '_'))
        os.makedirs(os.path.dirname(cache), exist_ok=True)

        try:
            with open(cache, 'rb') as f:
                return pickle.load(f)
        except IOError:
            result = func(*args)
            with open(cache, 'wb') as f:
                pickle.dump(result, f)
            return result
 
    return wrapper

@cache_info
def parse_us_cities_states_csv():
    us_cities_states_dict = {}
    fields = ['City', 'State short', 'City alias']
    df = pd.read_csv('./us_cities_states_counties.csv', sep='|', usecols=fields)

    for index, row in df.iterrows():
        us_cities_states_dict[row['City']] = row['State short']

        if row['City alias'] != '':
            us_cities_states_dict[row['City alias']] = row['State short']

    return us_cities_states_dict

def retrieve_href(string):
    return string.replace('location.href = \'', '').replace('\';', '')

def player_table_helper(players_per_page, offset, is_US):
    base_string = '{}/userAccount/s?max={}&offset={}&format=&showUsCitizensOnly=on' if is_US else '{}/userAccount/s?max={}&offset={}'
    players_href = base_string.format(URL, players_per_page, offset)
    players_request = requests.get(players_href)
    players_page = BeautifulSoup(players_request.text, 'html.parser')
    players_table = players_page.find_all('table')[1]

    return players_table

def find_num_players(is_US):
    base_string = '{}/userAccount/s?max=5&format=&showUsCitizensOnly=on' if is_US else '{}/userAccount/s?max=5'
    players_request = requests.get(base_string.format(URL))
    players_page = BeautifulSoup(players_request.text, 'html.parser')

    for span in players_page.find_all('span'):
        element = span.find('strong')
        if element:
            return int(element.text)

    return 0

def reformat_location(location):
    if len(location) in [2, 3]:
        return location.upper()
    return string.capwords(location.lower())

def parse_player_info(us_cities_states_dict, player_row):
    player_url = retrieve_href(player_row['onclick'])
    player_id = int(re.search(r'.*\/(.*)\?', player_url).group(1))
    rating = int(player_row.find_all('td')[6].text)
    locations = player_row.find_all('td')[5].text.split(',')
    main_location = reformat_location(locations[-1].strip())
    backup_location = reformat_location(locations[0].strip())
    selected_location = None

    if main_location == '':
        if backup_location == '':
            selected_location = ' OTHER'
        else:
            if backup_location in us_cities_states_dict:
                selected_location = us_cities_states_dict[backup_location]
            else:
                selected_location = ' OTHER'
    else:
        selected_location = main_location

    return player_id, rating, selected_location

def create_interval_tree():
    rating_intervals = IntervalTree()
    rating_intervals[0:250] = '0:250' 
    rating_intervals[250:500] = '251:500'
    rating_intervals[500:750] = '501:750'
    rating_intervals[750:1000] = '751:1000'
    rating_intervals[1000:1250] = '1001:1250'
    rating_intervals[1250:1500] = '1251:1500'
    rating_intervals[1500:1750] = '1501:1750'
    rating_intervals[1750:2000] = '1751:2000'
    rating_intervals[2000:2250] = '2001:2250'
    rating_intervals[2250:2500] = '2251:2500'
    rating_intervals[2500:4000] = '2501+'

    return rating_intervals

@cache_info
def get_preliminary_dicts(rating_intervals, us_cities_states_dict, offset=0, is_US=False, max_players_per_page=1000):
    player_info_dict = {}
    location_info_dict = {}
    num_players = None

    if USE_MAX:
        num_players = find_num_players(is_US)
    else:
        num_players = NUM_US_PLAYERS_LIMIT if is_US else NUM_INT_PLAYERS_LIMIT

    while offset < num_players:
        if USE_MAX and offset % 5000 == 0 and offset != 0:
            print('Completed information gathering for {} players.'.format(offset))
        players_per_page = num_players if num_players < max_players_per_page else max_players_per_page
        players_table = player_table_helper(players_per_page, offset, is_US)

        for player_row in players_table.find_all('tr', { 'class': 'list-item' }):
            player_id, rating, selected_location = parse_player_info(us_cities_states_dict, player_row)

            player_info_dict[player_id] = (selected_location, rating)
            rating_range = None

            try:
                rating_range = rating_intervals[rating].pop().data
            except:
                continue

            if rating_range in location_info_dict:
                if selected_location not in location_info_dict[rating_range]:
                    location_info_dict[rating_range][selected_location]  = { 'W': {}, 'L': {} }
            else:
                location_info_dict[rating_range] = {}
                location_info_dict[rating_range][selected_location] = { 'W': {}, 'L': {} }

        offset += players_per_page
        time.sleep(1)

    return player_info_dict, location_info_dict

# adds player to player_info_dict if not existent
def add_player(player_id, player_info_dict, us_cities_states_dict, nonexistent_usatt_ids):
    player_request = requests.get('{}/userAccount/up/{}'.format(URL, player_id))
    player_page = BeautifulSoup(player_request.text, 'html.parser')

    usatt_id = player_page.find('span', { 'class': ['title', 'less-margin'] }).findNext('small').text.split(': ')[1].strip()
    filter_request = requests.get('{}/userAccount/s?searchBy=usattNumber&query={}'.format(URL, usatt_id))
    filter_page = BeautifulSoup(filter_request.text, 'html.parser')

    try:
        table = filter_page.find_all('table')[1]
        player_row = table.find('tr', { 'class': 'list-item' })
        player_id, rating, selected_location = parse_player_info(us_cities_states_dict, player_row)

        player_info_dict[player_id] = (selected_location, rating)
        print('Added {} to player_info_dict.'.format(player_id))
    except:
        if usatt_id not in nonexistent_usatt_ids:
            print('USATT number {} does not exist.'.format(usatt_id))
            nonexistent_usatt_ids.append(usatt_id)

def find_num_tourneys():
    tourneys_href = '{}/t/search'.format(URL)
    tourneys_request = requests.get(tourneys_href)
    tourneys_page = BeautifulSoup(tourneys_request.text, 'html.parser')

    return int(tourneys_page.find('strong').text)

def get_tourney_ids(tourneys_per_page=100, offset=0):
    num_tourneys = find_num_tourneys() if USE_MAX else NUM_TOURNEYS_LIMIT
    tourney_ids = []

    if tourneys_per_page > num_tourneys:
        tourneys_per_page = num_tourneys

    while offset < num_tourneys:
        tourneys_href = '{}/t/search?max={}&offset={}'.format(URL, tourneys_per_page, offset)
        tourneys_request = requests.get(tourneys_href)
        tourneys_page = BeautifulSoup(tourneys_request.text, 'html.parser')
        tourneys_table = tourneys_page.find('table')

        for tourney in tourneys_table.find_all('tr', { 'class': 'list-item' }):
            tourney_url = retrieve_href(tourney['onclick'])
            tourney_id = int(re.search(r'.*\/(.*)\?', tourney_url).group(1))
            tourney_ids.append(tourney_id)

        offset += tourneys_per_page

    return tourney_ids

@cache_info
def get_main_info(rating_intervals, player_info_dict, location_info_dict, us_cities_states_dict, matches_per_page=100):
    def tourney_page_helper(offset, nonexistent_usatt_ids):
        num_matches = 0
        tourney_string = '{}/t/tr/{}?max={}&offset={}'.format(URL, tourney_id, matches_per_page, offset)
        apply_timeout = True
        tourney_request = None

        while apply_timeout:
            try:
                tourney_request = requests.get(tourney_string)
                apply_timeout = False
            except requests.exceptions.Timeout:
                print('Encountered timeout error. Waiting 60 seconds until trying again.')
                time.sleep(60)
            except ConnectionError:
                print('Connection has been aborted. Waiting 60 seconds until trying again.')
                time.sleep(60)
            except:
                print('Error has occurred. Waiting 60 seconds until trying again.')
                time.sleep(60)

        tourney_page = BeautifulSoup(tourney_request.text, 'html.parser')
        player_matches = tourney_page.find_all('td', { 'class': 'clickable' })

        for winner, loser in zip(player_matches[0::2], player_matches[1::2]):
            num_matches += 1
            winner_id = None
            loser_id = None

            try:
                winner_id = int(re.search(r'\?uai=(\d+)&', retrieve_href(winner['onclick'])).group(1))
                loser_id = int(re.search(r'\?uai=(\d+)&', retrieve_href(loser['onclick'])).group(1))
            except KeyError:
                continue

            if winner_id not in player_info_dict:
                if USE_MAX:
                    continue
                add_player(winner_id, player_info_dict, us_cities_states_dict, nonexistent_usatt_ids)

            if loser_id not in player_info_dict:
                if USE_MAX:
                    continue
                add_player(loser_id, player_info_dict, us_cities_states_dict, nonexistent_usatt_ids)

            try:
                winner_location, winner_rating = player_info_dict[winner_id]
                loser_location, loser_rating = player_info_dict[loser_id]
                winner_rating_interval = None
                loser_rating_interval = None

                try:
                    winner_rating_interval = rating_intervals[winner_rating].pop().data
                    loser_rating_interval = rating_intervals[loser_rating].pop().data
                except:
                    continue
            except:
                continue

            if loser_rating_interval not in location_info_dict:
                location_info_dict[loser_rating_interval] = {}
            if winner_rating_interval not in location_info_dict:
                location_info_dict[winner_rating_interval] = {}

            if loser_location not in location_info_dict[loser_rating_interval]:
                location_info_dict[loser_rating_interval][loser_location] = { 'W': {}, 'L': {} }
            if winner_location not in location_info_dict[winner_rating_interval]:
                location_info_dict[winner_rating_interval][winner_location] = { 'W': {}, 'L': {} }

            if winner_location in location_info_dict[loser_rating_interval][loser_location]['L']:
                # i.e. if the player loses to a higher-rated player, a positive number will be appended to the list.
                location_info_dict[loser_rating_interval][loser_location]['L'][winner_location].append(winner_rating - loser_rating)
            else:
                location_info_dict[loser_rating_interval][loser_location]['L'][winner_location] = [winner_rating - loser_rating]

            if loser_location in location_info_dict[winner_rating_interval][winner_location]['W']:
                # i.e. if the player beats a higher-rated player, a positive number will be appended to the list.
                location_info_dict[winner_rating_interval][winner_location]['W'][loser_location].append(loser_rating - winner_rating)
            else:
                location_info_dict[winner_rating_interval][winner_location]['W'][loser_location] = [loser_rating - winner_rating]
                

        return num_matches, tourney_page

    tourney_ids = get_tourney_ids()
    num_tourneys = len(tourney_ids)
    nonexistent_usatt_ids = []
    total_num_matches = 0

    for index, tourney_id in enumerate(tourney_ids):
        offset = 0

        if USE_MAX and index % 50 == 0 and index != 0:
            print('Completed information gathering for {} tournaments.'.format(index))

        num_matches, tourney_page = tourney_page_helper(offset, nonexistent_usatt_ids)
        total_num_matches += num_matches
        offset += matches_per_page
        offset_limit = None

        try:
            if (tourney_page.find('span', { 'class': ['step', 'gap'] })):
                offset_limit = int(re.search(r'offset=(\d+)', tourney_page.find('span', { 'class': ['step', 'gap'] }).next_sibling['href']).group(1))
            else:
                offset_limit = int(re.search(r'offset=(\d+)', tourney_page.find_all('a', { 'class': 'step'})[-1]['href']).group(1))
        except:
            offset_limit = 0

        while offset <= offset_limit:
            num_matches, tourney_page = tourney_page_helper(offset, nonexistent_usatt_ids)
            total_num_matches += num_matches
            offset += matches_per_page

            time.sleep(0.5)

        time.sleep(1)

    populated_location_info_dict = copy.deepcopy(location_info_dict)

    return total_num_matches, populated_location_info_dict

def calculate_statistics_helper(losses, wins):
    win_ratio = None
    num_losses = len(losses)
    num_wins = len(wins)

    try:
        win_ratio = num_wins / (num_wins + num_losses)
    except ZeroDivisionError:
        if num_wins > 0:
            win_ratio = 1
        else:
            win_ratio = 0

    return {
        'avg_win_rating_diff': numpy.mean(wins) if wins else 'N/A',
        'avg_loss_rating_diff': numpy.mean(losses) if losses else 'N/A',
        'median_win_rating_diff': numpy.median(wins) if wins else 'N/A',
        'median_loss_rating_diff': numpy.median(losses) if losses else 'N/A',
        'num_losses': num_losses,
        'num_wins': num_wins,
        'win_ratio': win_ratio
    }

def calculate_statistics(location_info_dict):
    location_stats = {}
    losses_by_state = None
    wins_by_state = None

    for rating_interval in location_info_dict:
        for location in location_info_dict[rating_interval]:
            losses_by_state = location_info_dict[rating_interval][location]['L']
            wins_by_state = location_info_dict[rating_interval][location]['W']
            states_stats = {}

            for state in losses_by_state:
                losses = losses_by_state[state]
                states_stats[state] = {
                    'avg_loss_rating_diff': numpy.mean(losses) if losses else 'N/A',
                    'avg_win_rating_diff': 'N/A',
                    'median_loss_rating_diff': numpy.median(losses) if losses else 'N/A',
                    'median_win_rating_diff': 'N/A',
                    'num_losses': len(losses) if losses else 'N/A',
                    'num_wins': 'N/A',
                    'win_ratio': 'N/A'
                }

            for state in wins_by_state:
                wins = wins_by_state[state]
                win_ratio = None

                if state in losses_by_state:
                    try:
                        win_ratio = len(wins) / (len(wins) + len(losses_by_state[state]))
                    except ZeroDivisionError:
                        win_ratio = 'N/A'
                else:
                    win_ratio = 'N/A'

                if state not in states_stats:
                    states_stats[state] = { 'avg_loss_rating_diff': 'N/A', 'median_loss_rating_diff': 'N/A', 'num_losses': 'N/A' }
                states_stats[state]['avg_win_rating_diff'] = numpy.mean(wins) if wins else 'N/A'
                states_stats[state]['median_win_rating_diff'] = numpy.median(wins) if wins else 'N/A'
                states_stats[state]['num_wins'] = len(wins) if wins else 'N/A'
                states_stats[state]['win_ratio'] = win_ratio

            aggregate_losses = list(itertools.chain(*losses_by_state.values()))
            aggregate_wins = list(itertools.chain(*wins_by_state.values()))

            if rating_interval not in location_stats:
                location_stats[rating_interval] = { location: {} }

            location_stats[rating_interval][location] = calculate_statistics_helper(aggregate_losses, aggregate_wins)
            location_stats[rating_interval][location]['states_stats'] = states_stats

    return location_stats

def create_rating_interval_statistics_worksheet(location_stats, stats, workbook):
    sorted_rating_intervals = sorted(list(location_stats.keys()), key=lambda interval: int(interval.split(':')[0].replace('+', '')))

    for rating_interval in sorted_rating_intervals:
        locations = set()
        states = set()

        for location in location_stats[rating_interval]:
            locations.add(location)

            if 'states_stats' in location_stats[rating_interval][location]:
                for state in location_stats[rating_interval][location]['states_stats']:
                    states.add(state)

        sorted_locations = sorted(list(locations), key=lambda loc: (len(loc), loc))
        sorted_states = sorted(list(states), key=lambda state: (len(state), state))
        sorted_states_index_mapping = { state: index for index, state in enumerate(sorted_states) }
        rating_interval_worksheet = workbook.add_worksheet('{} Statistics'.format(rating_interval.replace(':', ' to ')))
        stat_title_row_index = 0

        rating_interval_worksheet.set_column(0, 0, 20)

        for stat in stats:
            rating_interval_worksheet.write(stat_title_row_index, 0, stat, workbook.add_format({ 'bold': True, 'font_size': 20 }))

            for location_index, location in enumerate(sorted_locations):
                stat_table_row_index = stat_title_row_index + 2

                rating_interval_worksheet.write(stat_table_row_index + location_index + 1, 0, location, workbook.add_format({ 'bold': True, 'align': 'center' }))

                for state in sorted_states:
                    rating_interval_worksheet.write(stat_table_row_index, sorted_states_index_mapping[state] + 1, state, workbook.add_format({ 'bold': True, 'align': 'center' }))

                    if not location_stats[rating_interval][location]['states_stats'] or state not in location_stats[rating_interval][location]['states_stats']:
                        rating_interval_worksheet.write(stat_table_row_index + location_index + 1, sorted_states_index_mapping[state] + 1, 'N/A', workbook.add_format({ 'align': 'center' }))
                    elif stat in location_stats[rating_interval][location]['states_stats'][state]:
                        state_stat = location_stats[rating_interval][location]['states_stats'][state][stat]

                        rating_interval_worksheet.write(stat_table_row_index + location_index + 1, sorted_states_index_mapping[state] + 1, state_stat, workbook.add_format({ 'align': 'center' }))
                    else:
                        rating_interval_worksheet.write(stat_table_row_index + location_index + 1, sorted_states_index_mapping[state] + 1, 'N/A', workbook.add_format({ 'align': 'center' }))

            stat_title_row_index = stat_table_row_index + len(sorted_locations) + 2

def create_excel_workbook(location_stats, sorted_locations):
    if list(location_stats.keys()):
        workbook = xlsxwriter.Workbook('tt_statistics.xlsx')
        stats = sorted(['avg_loss_rating_diff', 'avg_win_rating_diff', 'median_loss_rating_diff', 'median_win_rating_diff', 'num_losses', 'num_wins', 'win_ratio'])

        create_rating_interval_statistics_worksheet(location_stats, stats, workbook)
        workbook.close()
    else:
        return print('Not enough data to create an excel workbook.')

def main():
    us_cities_states_dict = parse_us_cities_states_csv()
    print('Finished parsing csv file.')

    '''
    for large subsets of data, if we limit the player_info_dict to only US, then we fail to account for american players
    vs international players in certain matches. Individually adding the international players is an arduous process and
    adds to overhead, so we need to fill out the dictionary beforehand for all players (US and international).
    '''
    rating_intervals = create_interval_tree()
    player_info_dict, location_info_dict = get_preliminary_dicts(rating_intervals, us_cities_states_dict)
    print('Finished retrieving preliminary info.')
    print('Number of players in player_info_dict: {}\n'.format(len(player_info_dict)))

    total_num_matches, populated_location_info_dict = get_main_info(rating_intervals, player_info_dict, location_info_dict, us_cities_states_dict)
    print('Finished retrieiving main info from a total of {} matches.'.format(total_num_matches))

    sorted_locations = sorted(list(set(itertools.chain.from_iterable([list(location.keys()) for location in populated_location_info_dict.values()]))), key=lambda loc: (len(loc), loc))
    print('Locations: {}\n'.format(sorted_locations))

    if not USE_MAX:
        pprint(populated_location_info_dict)

    location_stats = calculate_statistics(populated_location_info_dict)
    print('Finished calculating statistics.')

    create_excel_workbook(location_stats, sorted_locations)
    print('Finished creating excel workbook.')

if __name__ == '__main__':
    main()
