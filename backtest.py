import argparse
import asyncio
import os
import pprint
from time import time

import numpy as np
import pandas as pd

from downloader import Downloader
from njit_funcs import njit_backtest_vanilla, njit_backtest_scalp, round_
from plotting import dump_plots
from procedures import prepare_backtest_config, make_get_filepath, load_live_config, add_argparse_args
from pure_funcs import create_xk, denumpyize, ts_to_date, analyze_fills, spotify_config, determine_config_type


def backtest(config: dict, data: np.ndarray, do_print=False) -> (list, bool):
    xk = create_xk(config)
    config_type = determine_config_type(config)
    if config_type == 'vanilla':
        return njit_backtest_vanilla(data, config['starting_balance'], config['latency_simulation_ms'],
                                     config['maker_fee'], **xk)
    elif config_type == 'scalp':
        return njit_backtest_scalp(data, config['starting_balance'], config['latency_simulation_ms'],
                                   config['maker_fee'], **xk)
    else:
        raise Exception('unknown config type')


def plot_wrap(config, data):
    print('n_days', round_(config['n_days'], 0.1))
    print('starting_balance', config['starting_balance'])
    print('backtesting...')
    sts = time()
    fills, info, stats = backtest(config, data, do_print=True)
    print(f'{time() - sts:.2f} seconds elapsed')
    if not fills:
        print('no fills')
        return
    fdf, result = analyze_fills(fills, {**config, **{'lowest_eqbal_ratio': info[1], 'closest_bkr': info[2]}},
                                data[0][0], data[-1][0])
    config['result'] = result
    config['plots_dirpath'] = make_get_filepath(os.path.join(
        config['plots_dirpath'], f"{ts_to_date(time())[:19].replace(':', '')}", '')
    )
    fdf.to_csv(config['plots_dirpath'] + "fills.csv")
    df = pd.DataFrame({**{'timestamp': data[:, 0], 'qty': data[:, 1], 'price': data[:, 2]},
                       **{}})
    print('dumping plots...')
    dump_plots(config, fdf, df)


async def main():
    parser = argparse.ArgumentParser(prog='Backtest', description='Backtest given passivbot config.')
    parser.add_argument('live_config_path', type=str, help='path to live config to test')
    parser = add_argparse_args(parser)
    args = parser.parse_args()

    config = await prepare_backtest_config(args)
    live_config = load_live_config(args.live_config_path)
    config_type = config['config_type'] = determine_config_type(live_config)
    config.update(live_config)
    if 'spot' in config['market_type']:
        live_config = spotify_config(live_config)
    downloader = Downloader(config)
    print()
    for k in (keys := ['exchange', 'spot', 'symbol', 'market_type', 'config_type', 'starting_balance', 'start_date', 'end_date',
                       'latency_simulation_ms']):
        if k in config:
            print(f"{k: <{max(map(len, keys)) + 2}} {config[k]}")
    print()
    data = await downloader.get_sampled_ticks()
    config['n_days'] = round_((data[-1][0] - data[0][0]) / (1000 * 60 * 60 * 24), 0.1)
    pprint.pprint(denumpyize(live_config))
    plot_wrap(config, data)


if __name__ == '__main__':
    asyncio.run(main())
