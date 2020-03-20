#!/usr/bin/env python3
import argparse
import concurrent.futures
import sys
import time
from collections import Counter, namedtuple
from enum import Enum

import requests
from tqdm import tqdm

Result = namedtuple('Result', 'status link')
HTTPStatus = Enum('Status', 'ok not_found error')


def final_report(links, counter, start_time):
    elapsed_time = time.time() - start_time
    print('-' * 20)
    print(f"{len(links)} link(s) tested.")
    print(f"{counter[HTTPStatus.ok]} link(s) ok.")
    if counter[HTTPStatus.not_found]:
        print(counter[HTTPStatus.not_found], 'not found.')
    if counter[HTTPStatus.error]:
        print(counter[HTTPStatus.error], 'error(s)')
    print(f'Elapsed time: {elapsed_time:.2f}s')


def get_args():
    parser = argparse.ArgumentParser(description='检查链接音源是否还可以播放',
                                     epilog='加班快乐👷')
    # parser.add_argument('-l',
    #                     '--length',
    #                     help='忽略能访问，但是Content-Length小于该值的连接',
    #                     type=int,
    #                     action='store',
    #                     default=100)
    parser.add_argument('-n',
                        '--num',
                        help='并发连接数',
                        type=int,
                        action='store',
                        default=10)
    parser.add_argument('-v', '--verbose', help='显示详细信息', action='store_true')
    parser.add_argument('infile',
                        nargs='?',
                        type=argparse.FileType('r'),
                        default=sys.stdin,
                        help='连接文件（每行一个连接）')
    args = parser.parse_args()
    links = []

    if args.num < 2:
        print('最少要2个并发吧')
        sys.exit()
    # if args.length < 100:
    #     print('最少100个长度得忽略吧')
    #     sys.exit()

    def chophead(link):
        return link.replace('\ufeff', '')

    links = tuple()

    if args.infile:
        links = args.infile.read().split()
        links = tuple(map(chophead, links))

    return args, links


def test_links(links, verbose=False, max_workers=10):
    def test_link(link):
        try:
            res = requests.get(link)
            if res.status_code != 200:
                res.raise_for_status()
        except requests.exceptions.HTTPError as exec:
            res = exec.response
            if res.status_code == 404:
                status = HTTPStatus.not_found
                msg = 'not found'
            else:
                raise
        else:
            status = HTTPStatus.ok
            msg = 'OK'

        if verbose:
            print(link, msg)

        return Result(status, link)

    counter = Counter()
    collection = {status: list() for status in HTTPStatus}

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(test_link, link): link
            for link in links
        }

        futures = concurrent.futures.as_completed(future_to_url)
        if not verbose:
            futures = tqdm(futures, total=len(links))

        for future in futures:
            link = future_to_url[future]
            try:
                res = future.result()
            except requests.exceptions.HTTPError as exec:
                error_msg = 'HTTP error {res.status_code} - {res.reason}'
                error_msg.format(res=exec.response)
            except requests.exceptions.ConnectionError:
                error_msg = 'Connection error'
            else:
                error_msg = ''
                status = res.status

            if error_msg:
                status = HTTPStatus.error
            counter[status] += 1
            collection[status].append(link)
            if verbose and error_msg:
                print('*** Error for {}: {}'.format(link, error_msg))
    return counter, collection


def main():
    args, links = get_args()
    start_time = time.time()
    counter, collection = test_links(links, args.verbose, args.num)
    final_report(links, counter, start_time)
    with open('fuck', 'w', encoding='utf8') as fp:
        fp.write('\r\n'.join(collection[HTTPStatus.ok]))


if __name__ == "__main__":
    main()
