#!/usr/bin/env python3
import argparse
import asyncio
import concurrent.futures
import sys
import time
from collections import Counter, namedtuple
from enum import Enum

import aiohttp
import requests
from tqdm import tqdm

Result = namedtuple("Result", "status link")
HTTPStatus = Enum("Status", "ok not_found error")


class FetchError(Exception):
    def __init__(self, link):
        self.link = link


async def test_link_async(session, link, semaphore, verbose):
    try:
        async with semaphore:
            res = await session.get(link)
            if res.status == 200:
                status = HTTPStatus.ok
                msg = "ok"
                data = await res.json()
                data = data["playlist"]
                print(
                    f"name: {data['name']}, shareCount: {data['shareCount']}, "
                    f"playCount: {data['playCount']}, subscribedCount: {data['subscribedCount']}"
                )

            elif res.status == 404:
                status = HTTPStatus.not_found
                msg = "not found"
            else:
                raise aiohttp.ClientError(
                    code=res.status, message=res.reason, headers=res.headers
                )
    except Exception as exc:
        raise FetchError(link) from exc

    if verbose:
        print(link, msg)

    return Result(status, link)


async def test_links_coro(links, verbose, concur_req):
    counter = Counter()
    collection = {status: list() for status in HTTPStatus}
    semaphore = asyncio.Semaphore(concur_req)
    async with aiohttp.ClientSession() as session:
        todo = [test_link_async(session, link, semaphore, verbose) for link in links]
        todo_iter = asyncio.as_completed(todo)
        if not verbose:
            todo_iter = tqdm(todo_iter, total=len(links))
        for future in todo_iter:
            try:
                res = await future
            except FetchError as exc:
                link = exc.link
                try:
                    error_msg = exc.__cause__.args[0]
                except IndexError:
                    error_msg = exc.__cause__.__class__.__name__
                if verbose and error_msg:
                    msg = "*** Error for {}: {}"
                    print(msg.format(link, error_msg))
                status = HTTPStatus.error
            else:
                link = res.link
                status = res.status

            collection[status].append(link)
            counter[status] += 1
    return counter, collection


def test_links_async(links, verbose, concur_req):
    loop = asyncio.get_event_loop()
    coro = test_links_coro(links, verbose, concur_req)
    # return asyncio.run(test_links_coro(links, verbose, concur_req))
    counter, collection = loop.run_until_complete(coro)
    loop.close()
    return counter, collection


def final_report(links, counter, start_time):
    elapsed_time = time.time() - start_time
    print("-" * 20)
    print(f"{len(links)} link(s) tested.")
    print(f"{counter[HTTPStatus.ok]} link(s) ok.")
    if counter[HTTPStatus.not_found]:
        print(counter[HTTPStatus.not_found], "not found.")
    if counter[HTTPStatus.error]:
        print(counter[HTTPStatus.error], "error(s)")
    print(f"Elapsed time: {elapsed_time:.2f}s")


def get_args():
    parser = argparse.ArgumentParser(description="检查链接音源是否还可以播放", epilog="加班快乐👷")
    parser.add_argument(
        "-n", "--num", help="并发连接数", type=int, action="store", default=10
    )
    parser.add_argument("-v", "--verbose", help="显示详细信息", action="store_true")
    # parser.add_argument(
    #     "infile",
    #     nargs="?",
    #     type=argparse.FileType("r"),
    #     default=sys.stdin,
    #     help="连接文件（每行一个连接）",
    # )
    args = parser.parse_args()
    links = []

    if args.num < 10:
        print("最少要10个并发吧")
        sys.exit()

    def chophead(link):
        return link.replace("\ufeff", "")

    links = tuple()

    links = [f"http://music163_api.dapps.douban.com/playlist/detail?id={x}" for x in range(5251500000, 5251510000)]

    # if args.infile:
    #     links = args.infile.read().split()
    #     links = tuple(map(chophead, links))

    return args, links


def test_many(links, verbose=False, max_workers=10):
    def test_link(link):
        try:
            res = requests.get(link)
            if res.status_code != 200:
                res.raise_for_status()
        except requests.exceptions.HTTPError as exec:
            res = exec.response
            if res.status_code == 404:
                status = HTTPStatus.not_found
                msg = "not found"
            else:
                raise
        else:
            status = HTTPStatus.ok
            msg = "OK"

        if verbose:
            print(link, msg)

        return Result(status, link)

    counter = Counter()
    collection = {status: list() for status in HTTPStatus}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(test_link, link): link for link in links}

        futures = concurrent.futures.as_completed(future_to_url)
        if not verbose:
            futures = tqdm(futures, total=len(links))

        for future in futures:
            link = future_to_url[future]
            try:
                res = future.result()
            except requests.exceptions.HTTPError as exec:
                error_msg = "HTTP error {res.status_code} - {res.reason}"
                error_msg.format(res=exec.response)
            except requests.exceptions.ConnectionError:
                error_msg = "Connection error"
            else:
                error_msg = ""
                status = res.status

            if error_msg:
                status = HTTPStatus.error
            counter[status] += 1
            collection[status].append(link)
            if verbose and error_msg:
                print("*** Error for {}: {}".format(link, error_msg))
    return counter, collection


def main():
    args, links = get_args()
    start_time = time.time()
    counter, collection = test_links_async(links, args.verbose, args.num)
    final_report(links, counter, start_time)
    # with open("fuck", "w", encoding="utf8") as fp:
    #     fp.write("\r\n".join(collection[HTTPStatus.ok]))


if __name__ == "__main__":
    main()
