from scrape.base import RequestsScraper, SeleniumScraper
from config import current_year, current_week

from selenium.webdriver.support import expected_conditions as cond
from selenium.webdriver.common.by import By

import re
import json


class GameListScraper(RequestsScraper):
    def __init__(self, url):
        super().__init__(url)

        def get_container():
            div = self.soup.find('div', id='all_games')
            return div.find('tbody')

        self.container = get_container()

    def get_week_links(self, week):
        cells = self.container.find_all('th', {'data-stat': 'week_num'}, text=week)
        return [GameListScraper.get_link(th.parent) for th in cells]

    @staticmethod
    def get_link(row):
        link = ''

        try:
            a = row.find('a', text='boxscore')
            link = prepend_link(a['href'])
        except AttributeError:
            pass

        return link


class PlayerListScraper(RequestsScraper):
    def __init__(self, url):
        super().__init__(url)

        def get_container():
            div = self.soup.find('div', id='all_fantasy')
            return div.find('tbody')

        self.container = get_container()

    def get_player_link(self, first, last):
        link = ''
        full_name = ' '.join((first, last))

        def get_link(name):
            a = self.container.find('a', text=name)
            return prepend_link(a['href'])

        def check_errors():
            error_name = errors['player_names'].get(full_name)
            return get_link(error_name) if error_name else prepend_link(errors['player_links'].get(full_name, ''))

        try:
            link = get_link(full_name)
        except TypeError:
            link = check_errors()

        return link


class GamePageScraper(SeleniumScraper):
    def __init__(self, url):
        super().__init__(url)
        self.scorebox = self.soup.find('div', attrs={'class': 'scorebox'})

    def interact_with_page(self):
        super().wait_for_condition(cond.presence_of_element_located(
            (By.ID, 'home_snap_counts')
        ))

        super().wait_for_condition(cond.presence_of_element_located(
            (By.ID, 'vis_snap_counts')
        ))

    def scrape_basic_info(self):
        def get_week():
            text = ''

            try:
                div = self.soup.find('div', id='div_other_scores')
                h2 = div.find('h2')
                a = h2.find('a')
                text = a.text.split(' ')[-1]
            except AttributeError:
                self.add_error('week')

            return text

        def scrape_scorebox():
            meta_div = self.scorebox.find('div', attrs={'class': 'scorebox_meta'})

            def get_meta_text(label):
                text = ''

                try:
                    strong = meta_div.find('strong', text=lambda x: label in x)
                    div = strong.parent
                    text = div.text.split(': ', 1)[1]
                except AttributeError:
                    self.add_error(label)

                return text

            def get_stadium():
                text = ''

                try:
                    strong = meta_div.find('strong', text=re.compile('Stadium'))
                    div = strong.parent
                    a = div.find('a')
                    text = a.text
                except AttributeError:
                    self.add_error('stadium')

                return text

            start_time_text = get_meta_text("Start Time")
            stadium_text = get_stadium()
            length_text = get_meta_text('Time of Game')

            return start_time_text, stadium_text, length_text

        start_time, stadium, length = scrape_scorebox()

        def scrape_game_info():
            div = self.soup.find('table', id='game_info')

            def get_row_value(label):
                th = div.find('th', {'data-stat': 'info'},
                              text=re.compile(label))

                return th.next_sibling.text

            roof_text = get_row_value('Roof')
            surface_text = get_row_value('Surface')
            spread_text = get_row_value('Vegas Line')
            over_under_text = get_row_value('Over/Under')

            return roof_text, surface_text, spread_text, over_under_text

        roof, surface, spread, over_under = scrape_game_info()

        self.data.update({
            'week': get_week(),
            'start_time': start_time,
            'stadium': stadium,
            'length': length,
            'roof': roof,
            'surface': surface,
            'spread': spread,
            'over_under': over_under,
        })

    def scrape_team_info(self):
        basic_info_divs = self.scorebox.find_all('div', attrs={'class': False},
                                                 recursive=False)

        snap_count_divs = [
            self.soup.find('table', id='home_snap_counts'),
            self.soup.find('table', id='vis_snap_counts')
        ]

        teams = []

        for index, team_div in enumerate(basic_info_divs):
            def scrape_team():
                def get_element_text(element, error_name):
                    text = ''

                    try:
                        text = element.text
                    except AttributeError:
                        self.add_error(error_name)

                    return text

                def get_snaps():
                    snaps = ''

                    def get_cells():
                        table = snap_count_divs[index]

                        def get_percent_cell():
                            cell = table.find('td', {'data-stat': 'off_pct'},
                                                 text=re.compile('100%'))

                            if not cell:
                                cell = table.find('td', {'data-stat': 'off_pct'},
                                              text=lambda x: x != '0%')

                            return cell

                        percent = get_percent_cell()
                        row = percent.parent
                        amount = row.find('td', {'data-stat': 'offense'})

                        return percent, amount

                    try:
                        percent_cell, amount_cell = get_cells()

                        def calculate_snaps():
                            def get_percent():
                                text = percent_cell.text.split('%')[0]
                                return int(text)

                            percent = get_percent()
                            amount = int(amount_cell.text)
                            result = percent * 0.01 * amount
                            return round(result)

                        snaps = calculate_snaps()
                    except AttributeError:
                        self.add_error('snaps')

                    return snaps

                return {
                    'name': get_element_text(
                        team_div.find('a', {'itemprop': 'name'}), 'name'),
                    'score': get_element_text(
                        team_div.find('div', attrs={'class': 'score'}), 'score'),
                    'snaps': get_snaps()
                }

            teams.append(scrape_team())

        self.data.update({'team_games': teams})


class PlayerPageScraper(RequestsScraper):
    def __init__(self, url, year=current_year):
        self.year = year

        def format_gamelog_url():
            append = '/gamelog/%s/' % self.year
            return re.sub('.htm$', append, url)

        super().__init__(format_gamelog_url())
        self.data['games'] = []

    def scrape_basic_info(self):
        container = self.soup.find('div', id='meta')

        def get_name():
            first_text = ''
            last_text = ''
            h1 = container.find('h1', {'itemprop': 'name'})

            try:
                full_name = h1.text
                split_name = full_name.split(' ', 1)
                first_text = split_name[0]
                last_text = split_name[1]
            except (IndexError, AttributeError):
                self.add_error('name')

            return first_text, last_text

        def get_team():
            text = ''
            span = container.find('span', {'itemprop': 'affiliation'})

            try:
                text = span.text
            except AttributeError:
                self.add_error('team')

            return text

        def get_birth_date():
            year = ''
            month = ''
            day = ''

            span = container.find('span', id='necro-birth')

            try:
                text = span['data-birth']
                split_text = text.split('-')
                year = split_text[0]
                month = split_text[1]
                day = split_text[2]
            except (TypeError, IndexError):
                self.add_error('birth_date')

            return year, month, day

        first, last = get_name()
        birth_year, birth_month, birth_day = get_birth_date()

        self.data.update({
            'first': first,
            'last': last,
            'team': get_team(),
            'birth_year': birth_year,
            'birth_month': birth_month,
            'birth_day': birth_day
        })

    def scrape_game_stats(self, week=current_week):
        def get_row():
            td = self.soup.find('td', {'data-stat': 'week_num'}, text=week)
            return td.parent

        try:
            row = get_row()

            def get_datastat_text(label):
                text = '0'
                td = row.find('td', {'data-stat': label})

                try:
                    text = td.text
                except AttributeError:
                    pass

                return text

            self.data['games'].append({
                'year': self.year,
                'week': week,
                'team': get_datastat_text('team'),
                'rush_att': get_datastat_text('rush_att'),
                'rush_yd': get_datastat_text('rush_yds'),
                'rush_td': get_datastat_text('rush_td'),
                'fum': get_datastat_text('fumbles'),
                'tgt': get_datastat_text('targets'),
                'rec': get_datastat_text('rec'),
                'rec_yd': get_datastat_text('rec_yds'),
                'rec_td': get_datastat_text('rec_td'),
                'pass_att': get_datastat_text('pass_att'),
                'pass_cmp': get_datastat_text('pass_cmp'),
                'pass_yd': get_datastat_text('pass_yds'),
                'pass_td': get_datastat_text('pass_td'),
                'int': get_datastat_text('pass_int'),
                'sacked': get_datastat_text('pass_sacked'),
                'snaps': get_datastat_text('offense')
            })
        except AttributeError:
            pass


def scrape_player(link, year=current_year, weeks=current_week):
    player = PlayerPageScraper(link, year)
    player.scrape_basic_info()

    def scrape_games():
        for week in weeks:
            player.scrape_game_stats(week)

    try:
        scrape_games()
    except TypeError:
        weeks = [weeks]
        scrape_games()

    return player.data


def scrape_game(link):
    game = GamePageScraper(link)
    game.scrape_basic_info()
    game.scrape_team_info()
    return game.data


# Utilities
with open('./scrape/error/pfr.json') as file:
    errors = json.load(file)


def prepend_link(link):
    return 'https://www.pro-football-reference.com' + link
