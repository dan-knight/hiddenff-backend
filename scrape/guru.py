from scrape.base import RequestsScraper

from io import StringIO


class PlayerListScraper(RequestsScraper):
    pass

    def get_player_links(self):
        container = self.soup.find('pre')
        link_tags = container.find_all('a', href=lambda href: href.startswith('playrf'))
        return [prepend_link(tag['href']) for tag in link_tags]


class PlayerPageScraper(RequestsScraper):
    def __init__(self, url):
        super().__init__(url)
        self.data['games'] = []

    def scrape_basic_info(self):
        def get_name():
            first_text = ''
            last_text = ''

            container = self.soup.find('font', size=3)

            def add_error():
                self.data['errors'].append('name')

            try:
                full_name = container.find('b').text

                def split_name(separator):
                    split = full_name.split(separator)
                    return split[0], split[1]

                try:
                    last_text, first_text = split_name(', ')
                except IndexError:
                    if 'Defense' in full_name:
                        first_text, last_text = split_name(' ')
                    else:
                        add_error()
            except AttributeError:
                add_error()

            return first_text, last_text

        def get_position():
            text = ''
            label = self.soup.find(text='DraftKings position: ')

            try:
                text = label.next_sibling.text
            except AttributeError:
                self.data['errors'].append('position')

            return text

        first, last = get_name()

        self.data.update({
            'first': first,
            'last': last,
            'position': get_position()
        })


def scrape_week():
    player_list_url = 'http://rotoguru1.com/cgi-bin/fstats.cgi?pos=0&sort=1&game=p&colA=0&daypt=0&xavg=0&inact=0&maxprc=99999&outcsv=0'

    player_links = PlayerListScraper(player_list_url).get_player_links()

    return [scrape_player(link) for link in player_links]


def scrape_player(link):
    player = PlayerPageScraper(link)
    player.scrape_basic_info()
    return player.data


# Utilities
def prepend_link(link):
    return 'http://rotoguru1.com/cgi-bin/' + link
