import itertools
import numpy
import re
import requests
import xlsxwriter

from bs4 import BeautifulSoup

URL = 'https://usatt.simplycompete.com'
NUM_PLAYERS = 50000
US_ONLY = True

# helper function to reformat parsed html hrefs
def retrieve_href(string):
    return string.replace('location.href = \'', '').replace('\';', '')

# gets a list of relevant players
def get_players_table():
    players_href = '{}/userAccount/s?max={}&showUsCitizensOnly=on' if US_ONLY else '{}/userAccount/s?max={}'
    players_request = requests.get(players_href.format(URL, NUM_PLAYERS))
    players_page = BeautifulSoup(players_request.text, 'html.parser')
    players_table = players_page.find_all('table')[1]

    return players_table

# adds player to player_info_dict if not existent
def add_player(player_id, player_info_dict, nonexistent_usatt_ids):
    player_request = requests.get('{}/userAccount/up/{}'.format(URL, player_id))
    player_page = BeautifulSoup(player_request.text, 'html.parser')

    usatt_id = player_page.find('span', { 'class': ['title', 'less-margin'] }).findNext('small').text.split(': ')[1]

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
            nonexistent_usatt_ids.append(usatt_id)
            print('USATT number does not exist using this link: {}/userAccount/s?searchBy=usattNumber&query={}'.format(URL, usatt_id))

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
def get_main_info(players_table, player_info_dict, location_info_dict):
    for index, player_row in enumerate(players_table.find_all('tr', { 'class': 'list-item' })):
        if NUM_PLAYERS > 50:
            if index == NUM_PLAYERS // 4 or index == NUM_PLAYERS // 2 or index == 3 * NUM_PLAYERS // 4:
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
                winner_id = int(re.search(r'\?uai=(\d+)&', retrieve_href(winner['onclick'])).group(1))
                loser_id = re.search(r'\?uai=(\d+)&', retrieve_href(loser['onclick'])).group(1)
                player_location, player_rating = player_info_dict[player_id]
                outcome = None
                opponent_id = None

                if winner_id is player_id:
                    outcome = 'W'
                    opponent_id = loser_id
                else:
                    outcome = 'L'
                    opponent_id = winner_id

                if opponent_id not in player_info_dict:
                    # speeds up script considerably
                    if US_ONLY:
                        continue
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

# get all relevant statistics here
def calculate_statistics(location_info_dict):
    location_stats = {}

    for location in location_info_dict:
        losses_by_state = location_info_dict[location]['L']
        wins_by_state = location_info_dict[location]['W']
        losses = list(itertools.chain(*losses_by_state.values()))
        wins = list(itertools.chain(*wins_by_state.values()))
        win_ratio = None

        try:
            win_ratio = len(wins) / (len(wins) + len(losses))
        except ZeroDivisionError:
            win_ratio = 'N/A'

        avg_win_rating_diff = numpy.mean(wins) if wins else 'N/A'
        avg_loss_rating_diff = numpy.mean(losses) if losses else 'N/A'
        median_win_rating_diff = numpy.median(wins) if wins else 'N/A'
        median_loss_rating_diff = numpy.median(losses) if losses else 'N/A'

        location_stats[location] = { 'win_ratio': win_ratio,
                                     'avg_win_rating_diff': avg_win_rating_diff,
    				                 'avg_loss_rating_diff': avg_loss_rating_diff,
    				                 'median_win_rating_diff': median_win_rating_diff,
    				                 'median_loss_rating_diff': median_loss_rating_diff }

    return location_stats

def create_excel_workbook(location_stats):
    if list(location_stats.keys()):
        workbook = xlsxwriter.Workbook('tt_statistics.xlsx')
        worksheet = workbook.add_worksheet('State Statistics')

        worksheet.set_column(0, 0, 20)

        for x_index, stat in enumerate(location_stats[list(location_stats.keys())[0]], 1):
            worksheet.write(x_index, 0, stat)

        for y_index, location in enumerate(location_stats.keys(), 1):
            worksheet.write(0, y_index, location)

            for x_index, stat in enumerate(location_stats[location].values(), 1):
                worksheet.write(x_index, y_index, stat)

        workbook.close()

if __name__ == '__main__':
    player_info_dict = {}
    location_info_dict = {}
    nonexistent_usatt_ids = []

    players_table = get_players_table()

    get_preliminary_info(players_table, player_info_dict, location_info_dict)
    print('Finished retrieving preliminary info.')
    print('Number of players: {}'.format(len(player_info_dict)))

    get_main_info(players_table, player_info_dict, location_info_dict)
    print('Finished retrieiving main info.')
    print(location_info_dict.keys())

    location_stats = calculate_statistics(location_info_dict)
    print('Finished calculating statistics.')

    create_excel_workbook(location_stats)