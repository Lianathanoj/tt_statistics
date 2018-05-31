import itertools
import numpy
import re
import requests
import xlsxwriter

from bs4 import BeautifulSoup

URL = 'https://usatt.simplycompete.com'

# helper function to reformat parsed html hrefs
def retrieve_href(string):
    return string.replace('location.href = \'', '').replace('\';', '')

# gets a list of relevant players
def get_players_table(is_US=True):
    players_href = '{}/userAccount/s?max={}&showUsCitizensOnly=on' if is_US else '{}/userAccount/s?max={}'
    players_request = requests.get(players_href.format(URL, NUM_PLAYERS))
    players_page = BeautifulSoup(players_request.text, 'html.parser')
    players_table = players_page.find_all('table')[1]

    return players_table

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

        player_info_dict[player_id] = (location, rating)
        print('Added {} to player_info_dict.'.format(player_id))
    except:
        if usatt_id not in nonexistent_usatt_ids:
            print('USATT number {} does not exist.'.format(usatt_id))
            nonexistent_usatt_ids.append(usatt_id)

# find all players and apply mapping to a dict of player --> region, rating
# setup location dict for each state
def get_preliminary_info(players_table, player_info_dict, location_info_dict):
    for player_row in players_table.find_all('tr', { 'class': 'list-item' }):
        player_url = retrieve_href(player_row['onclick'])
        player_id = int(re.search(r'.*\/(.*)\?', player_url).group(1))
        location = player_row.find_all('td')[5].text.split(',')[-1].strip()
        rating = int(player_row.find_all('td')[6].text)

        player_info_dict[player_id] = (location, rating)
        location_info_dict[location] = { 'W': {}, 'L': {} }

# get rating difference for match winners and losers
def get_main_info(players_table, player_info_dict, location_info_dict, nonexistent_usatt_ids):
    for index, player_row in enumerate(players_table.find_all('tr', { 'class': 'list-item' })):
        if NUM_PLAYERS > 50 and index % (NUM_PLAYERS // 10):
            print('Finished retrieiving info for {} players'.format(index))

        player_url = retrieve_href(player_row['onclick'])
        player_id = int(re.search(r'.*\/(.*)\?', player_url).group(1))
        player_tourneys_request = requests.get('{}/userAccount/trn/{}'.format(URL, player_id))
        player_tourneys_page = BeautifulSoup(player_tourneys_request.text, 'html.parser')

        for tournament in player_tourneys_page.find_all('tr', { 'class': 'list-item' }):
            player_tourney_string = retrieve_href(tournament['onclick'])
            player_matches_request = requests.get('{}{}'.format(URL, player_tourney_string))
            player_matches_page = BeautifulSoup(player_matches_request.text, 'html.parser')
            player_matches = player_matches_page.find_all('td', { 'class': 'clickable' })

            for winner, loser in zip(player_matches[0::2], player_matches[1::2]):
                winner_id = None
                loser_id = None

                try:
                    winner_id = int(re.search(r'\?uai=(\d+)&', retrieve_href(winner['onclick'])).group(1))
                    loser_id = int(re.search(r'\?uai=(\d+)&', retrieve_href(loser['onclick'])).group(1))
                except KeyError:
                    continue

                player_location, player_rating = player_info_dict[player_id]
                outcome, opponent_id = ('W', loser_id) if winner_id == player_id else ('L', winner_id)

                if opponent_id not in player_info_dict:
                    # continue
                    add_player(opponent_id, player_info_dict, nonexistent_usatt_ids)

                try:
                    opponent_location, opponent_rating = player_info_dict[opponent_id]
                except:
                    continue

                if opponent_location in location_info_dict[player_location][outcome]:
                    # i.e. if the current player beats a higher-rated player, a negative number will be appended to the list
                    location_info_dict[player_location][outcome][opponent_location].append(player_rating - opponent_rating)
                else:
                    location_info_dict[player_location][outcome][opponent_location] = []

def calculate_statistics_helper(losses, wins):
    win_ratio = None
    num_losses = len(losses)
    num_wins = len(wins)

    try:
        win_ratio = num_wins / (num_wins + num_losses)
    except ZeroDivisionError:
        win_ratio = 'N/A'

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
    sorted_locations = sorted(location_stats.keys())
    sorted_states = list(set(itertools.chain.from_iterable([list(location_stats[location]['states_stats'].keys()) for location in location_stats])))
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
    player_info_dict = {}
    location_info_dict = {}
    nonexistent_usatt_ids = []

    players_table = get_players_table(is_US=False)

    get_preliminary_info(players_table, player_info_dict, location_info_dict)
    print('Finished retrieving preliminary info.')
    print('Number of players: {}\n'.format(len(player_info_dict)))


    '''
    for large subsets of data, if we limit it to only US, then we fail to account for american players
    vs international players. Individually adding the international players is an arduous process, so
    if we fill the dictionary beforehand for all players and then limit to US for getting the main info,
    we can speed up the script.
    '''

    get_main_info(players_table, player_info_dict, location_info_dict, nonexistent_usatt_ids)
    print('Finished retrieiving main info.')
    print('Locations: {}\n'.format(list(location_info_dict.keys())))
    # print(location_info_dict)

    location_stats = calculate_statistics(location_info_dict)
    # print(location_stats)
    print('Finished calculating statistics.')

    create_excel_workbook(location_stats)

if __name__ == '__main__':
    main()
