import itertools
import numpy
import re
import requests
import time
import xlsxwriter

from bs4 import BeautifulSoup

NUM_INT_PLAYERS_LIMIT = 5
NUM_US_PLAYERS_LIMIT = 5
NUM_TOURNEYS_LIMIT = 3
MAX_PLAYERS_PER_PAGE = 1000
URL = 'https://usatt.simplycompete.com'
USE_MAX = True

# helper function to reformat parsed html hrefs
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

def get_preliminary_dicts(offset=0, is_US=True):
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
        players_per_page = num_players if num_players < MAX_PLAYERS_PER_PAGE else MAX_PLAYERS_PER_PAGE
        players_table = player_table_helper(players_per_page, offset, is_US)

        for player_row in players_table.find_all('tr', { 'class': 'list-item' }):
            player_url = retrieve_href(player_row['onclick'])
            player_id = int(re.search(r'.*\/(.*)\?', player_url).group(1))
            location = player_row.find_all('td')[5].text.split(',')[-1].strip()
            location = ' UNKNOWN' if location is '' else location
            rating = int(player_row.find_all('td')[6].text)

            player_info_dict[player_id] = (location, rating)
            location_info_dict[location] = { 'W': {}, 'L': {} }

        offset += players_per_page
        time.sleep(1)

    return player_info_dict, location_info_dict

# adds player to player_info_dict if not existent
def add_player(player_id, player_info_dict, nonexistent_usatt_ids):
    player_request = requests.get('{}/userAccount/up/{}'.format(URL, player_id))
    player_page = BeautifulSoup(player_request.text, 'html.parser')

    usatt_id = player_page.find('span', { 'class': ['title', 'less-margin'] }).findNext('small').text.split(': ')[1].strip()
    filter_request = requests.get('{}/userAccount/s?searchBy=usattNumber&query={}'.format(URL, usatt_id))
    filter_page = BeautifulSoup(filter_request.text, 'html.parser')

    try:
        table = filter_page.find_all('table')[1]
        player_row = table.find('tr', { 'class': 'list-item' })
        player_url = retrieve_href(player_row['onclick'])
        player_id = int(re.search(r'.*\/(.*)\?', player_url).group(1))
        location = player_row.find_all('td')[5].text.split(',')[-1].strip()
        rating = int(player_row.find_all('td')[6].text)

        player_info_dict[player_id] = (' UNKNOWN' if location is '' else location, rating)
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
    tourney_ids = []
    num_tourneys = find_num_tourneys() if USE_MAX else NUM_TOURNEYS_LIMIT

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

# get rating difference for match winners and losers
def get_main_info(player_info_dict, location_info_dict, matches_per_page=100):
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
                    # print('Skipping {}'.format(winner_id))
                    continue
                add_player(winner_id, player_info_dict, nonexistent_usatt_ids)

            if loser_id not in player_info_dict:
                if USE_MAX:
                    # print('Skipping {}'.format(loser_id))
                    continue
                add_player(loser_id, player_info_dict, nonexistent_usatt_ids)

            try:
                winner_location, winner_rating = player_info_dict[winner_id]
                loser_location, loser_rating = player_info_dict[loser_id]
            except:
                continue

            if loser_location not in location_info_dict:
                location_info_dict[loser_location] = { 'W': {}, 'L': {} }
            if winner_location not in location_info_dict:
                location_info_dict[winner_location] = { 'W': {}, 'L': {} }

            if winner_location in location_info_dict[loser_location]['L']:
                # i.e. if the player loses to a higher-rated player, a positive number will be appended to the list.
                location_info_dict[loser_location]['L'][winner_location].append(winner_rating - loser_rating)
            else:
                location_info_dict[loser_location]['L'][winner_location] = [winner_rating - loser_rating]

            if loser_location in location_info_dict[winner_location]['W']:
                # i.e. if the player beats a higher-rated player, a positive number will be appended to the list.
                location_info_dict[winner_location]['W'][loser_location].append(loser_rating - winner_rating)
            else:
                location_info_dict[winner_location]['W'][loser_location] = [loser_rating - winner_rating]

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

    return total_num_matches

def calculate_statistics_helper(losses, wins):
    win_ratio = None
    num_losses = len(losses)
    num_wins = len(wins)

    try:
        win_ratio = num_wins / (num_wins + num_losses)
    except ZeroDivisionError:
        win_ratio = 1

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

    for location in location_info_dict:
        losses_by_state = location_info_dict[location]['L']
        wins_by_state = location_info_dict[location]['W']
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

        location_stats[location] = calculate_statistics_helper(aggregate_losses, aggregate_wins)
        location_stats[location]['states_stats'] = states_stats

    return location_stats

def create_aggregated_statistics_worksheet(location_stats, workbook):
    aggregate_states_worksheet = workbook.add_worksheet('State Aggregated Statistics')
    first_location = list(location_stats.keys())[0]

    aggregate_states_worksheet.set_column(0, 0, 20)

    for row_index, stat_name in enumerate(sorted([stat_name for stat_name in location_stats[first_location].keys() if stat_name is not 'states_stats']), 1):
        aggregate_states_worksheet.write(row_index, 0, stat_name, workbook.add_format({ 'bold': True }))

    for col_index, location in enumerate(sorted(location_stats.keys()), 1):
        aggregate_states_worksheet.write(0, col_index, location, workbook.add_format({ 'bold': True, 'align': 'center' }))

        for row_index, stat_name in enumerate(sorted([stat_name for stat_name in location_stats[location].keys() if stat_name is not 'states_stats']), 1):
            try:
                if stat_name is not 'states_stats':
                    aggregate_states_worksheet.write(row_index, col_index, location_stats[location][stat_name], workbook.add_format({ 'align': 'center' }))
            except TypeError:
                continue

def create_state_statistics_worksheet(location_stats, workbook):
    states_worksheet = workbook.add_worksheet('State Statistics')
    stats = sorted(['avg_loss_rating_diff', 'avg_win_rating_diff', 'median_loss_rating_diff', 'median_win_rating_diff', 'num_losses', 'num_wins', 'win_ratio'])
    stat_title_row_index = 0
    sorted_locations = sorted([location for location in location_stats if location_stats[location]['states_stats']])
    sorted_states = sorted(list(set(itertools.chain.from_iterable([list(location_stats[location]['states_stats'].keys()) for location in location_stats]))))
    sorted_states_index_mapping = { state: index for index, state in enumerate(sorted_states) }

    states_worksheet.set_column(0, 0, 20)

    for stat in stats:
        states_worksheet.write(stat_title_row_index, 0, stat, workbook.add_format({ 'bold': True, 'font_size': 20 }))
        for location_index, location in enumerate(sorted_locations):
            stat_table_row_index = stat_title_row_index + 2

            states_worksheet.write(stat_table_row_index + location_index + 1, 0, location, workbook.add_format({ 'bold': True, 'align': 'center' }))

            for state in sorted_states:
                states_worksheet.write(stat_table_row_index, sorted_states_index_mapping[state] + 1, state, workbook.add_format({ 'bold': True, 'align': 'center' }))

                if not location_stats[location]['states_stats'] or state not in location_stats[location]['states_stats']:
                    states_worksheet.write(stat_table_row_index + location_index + 1, sorted_states_index_mapping[state] + 1, 'N/A', workbook.add_format({ 'align': 'center' }))
                elif stat in location_stats[location]['states_stats'][state]:
                    state_stat = location_stats[location]['states_stats'][state][stat]

                    states_worksheet.write(stat_table_row_index + location_index + 1, sorted_states_index_mapping[state] + 1, state_stat, workbook.add_format({ 'align': 'center' }))
                else:
                    states_worksheet.write(stat_table_row_index + location_index + 1, sorted_states_index_mapping[state] + 1, 'N/A', workbook.add_format({ 'align': 'center' }))

        stat_title_row_index = stat_table_row_index + len(sorted_locations) + 2

def create_excel_workbook(location_stats):
    if list(location_stats.keys()):
        workbook = xlsxwriter.Workbook('tt_statistics.xlsx')

        create_aggregated_statistics_worksheet(location_stats, workbook)
        create_state_statistics_worksheet(location_stats, workbook)
        workbook.close()
    else:
        return print('Not enough data to create an excel workbook.')

def main():
    '''
    for large subsets of data, if we limit the player_info_dict to only US, then we fail to account for american players
    vs international players in certain matches. Individually adding the international players is an arduous process and
    adds to overhead, so we need to fill out the dictionary beforehand for all players (US and international).
    '''

    player_info_dict, location_info_dict = get_preliminary_dicts(is_US=False)
    print('Finished retrieving preliminary info.')
    print('Number of players in player_info_dict: {}\n'.format(len(player_info_dict)))

    total_num_matches = get_main_info(player_info_dict, location_info_dict)
    print('\nFinished retrieiving main info from a total of {} matches.'.format(total_num_matches))
    print('Locations: {}\n'.format(list(location_info_dict.keys())))
    # print(location_info_dict)

    location_stats = calculate_statistics(location_info_dict)
    # print(location_stats)
    print('Finished calculating statistics.')

    create_excel_workbook(location_stats)

if __name__ == '__main__':
    main()
