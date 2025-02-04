from os.path import dirname as up
import os
from PIL import Image, ImageDraw, ImageFont
import ravelin_functions as rf
import sqlalchemy as db
import pickle
import asyncio


async def get_stats_img():
    parent_dir = os.path.abspath(up(__file__))
    filepath_files = os.path.join(up(parent_dir), 'files')

    get_data = rf.BlockchainData

    info_dict = await get_data("MILKOMEDA", "OccamX").get_ravelin_stats()

    rshare_locked_value = '{:0.2f}'.format(float(info_dict['rshare_locked'])*float(info_dict['rshare_price']))
    rshare_locked_value = '{:,}'.format(float(rshare_locked_value))
    rshare_tvl = '{:0.2f}'.format(info_dict['rshare_tvl'])
    rshare_tvl = '{:,}'.format(float(rshare_tvl))
    rav_tvl = '{:0.2f}'.format(info_dict['rav_tvl'])
    rav_tvl = '{:,}'.format(float(rav_tvl))



    title_font = ImageFont.truetype(filepath_files+'/Inter/Inter-Regular.ttf', 25)
    title_font_bold = ImageFont.truetype(filepath_files+'/Inter/Inter-Bold.ttf', 25)
    bit_bigger_font = ImageFont.truetype(filepath_files+'/Inter/Inter-Bold.ttf', 30)
    bigger_font = ImageFont.truetype(filepath_files+'/Inter/Inter-Bold.ttf', 36)
    smaller_font = ImageFont.truetype(filepath_files+'/Inter/Inter-Regular.ttf', 20)
    smallest_font = ImageFont.truetype(filepath_files+'/Inter/Inter-Regular.ttf', 22)
    price_font = ImageFont.truetype(filepath_files+'/Inter/Inter-Regular.ttf', 36)
    price_font_small = ImageFont.truetype(filepath_files+'/Inter/Inter-Regular.ttf', 26)


    # RAV PRICE
    rav_price_text = f"${info_dict['rav_price']}"
    rav_twap_text = f"TWAP:\nx{info_dict['peg']}"
    if float(info_dict['peg']) >= 1.01:
        my_image = Image.open(filepath_files+"/stats_pic.png")
        peg_status = (0, 78, 10)
    else:
        my_image = Image.open(filepath_files+"/stats_pic_rbond.png")
        peg_status = (84, 0, 0)
    image_editable = ImageDraw.Draw(my_image)

    image_editable.text((134,290), rav_price_text, (96, 96, 96), font=price_font)
    image_editable.text((170,358), rav_twap_text, peg_status, font=price_font_small)

    # RSHARE PRICE
    rshare_price_text = f"${info_dict['rshare_price']}"
    rshare_staked = f"In Boardroom:\n {info_dict['rshare_locked']} ({info_dict['rshare_locked_pct']}%)"
    image_editable.text((660,290), rshare_price_text, (96, 96, 96), font=price_font)
    image_editable.text((660,358), rshare_staked, (96, 96, 96), font=price_font_small)

    # ADA
    ada_price_text = f"${info_dict['ada_price']}"
    image_editable.text((428,419), ada_price_text, (96, 96, 96), font=price_font_small)

    # TVL
    tvl_text = f"${'{:,}'.format(float(info_dict['tvl']))}"
    tvl_text_2 = f"    Excluding\n"\
                 f"Genesis Pools"

    image_editable.text((400,138), tvl_text, (96, 96, 96), font=price_font_small)
    image_editable.text((413,185), tvl_text_2, (96, 96, 96), font=smaller_font)

    # RAV LP
    rav_lp_price_text = f"LP Price:\n" \
                        f"Daily ROI:\n" \
                        f"APR:\n" \
                        f"TVL:"
    rav_lp_price_text_2 = f"${info_dict['rav_lp_price']}\n" \
                          f"{info_dict['rav_mada_apr']}%\n" \
                          f"{'{:0.2f}'.format(float(info_dict['rav_mada_apr'])*365)}%\n" \
                          f"${rav_tvl}"
    image_editable.text((70,605), rav_lp_price_text, (126, 126, 126), font=title_font_bold)
    image_editable.text((205,605), rav_lp_price_text_2, (96, 96, 96), font=title_font)

    # RSHARE LP
    rshare_lp_price_text = f"LP Price:\n" \
                           f"Daily ROI:\n" \
                           f"APR:\n" \
                           f"TVL:"
    rshare_lp_price_text_2 = f"${info_dict['rshare_lp_price']}\n" \
                          f"{info_dict['rshare_mada_apr']}%\n" \
                          f"{'{:0.2f}'.format(float(info_dict['rshare_mada_apr'])*365)}%\n" \
                          f"${rshare_tvl}"
    image_editable.text((540,605), rshare_lp_price_text, (126, 126, 126), font=title_font_bold)
    image_editable.text((675,605), rshare_lp_price_text_2, (96, 96, 96), font=title_font)

    # EPOCHS
    current_epoch_text = f"Current Epoch: {info_dict['current_epoch']}"

    next_epoch_text = f"Next Epoch In:"
    next_epoch_text_2 = f"{info_dict['next_epoch']}"
    if "-" in str(next_epoch_text_2):
        next_epoch_text = ""
        next_epoch_text_2 = f"Allocate Rewards!"
    image_editable.text((82,820), current_epoch_text, (86, 86, 86), font=bigger_font)
    image_editable.text((610,800), next_epoch_text, (86, 86, 86), font=bit_bigger_font)
    image_editable.text((600,840), next_epoch_text_2, (86, 86, 86), font=bigger_font)

    # RSHARE BOARDROOM
    rshare_staked_text = f"RSHARE Staked"
    rshare_staked_text_2 = f"Amount:\n" \
                        f"Worth:\n" \
                        f"Percentage:"
    rshare_staked_text_3 = f"{info_dict['rshare_locked']}\n" \
                           f"${rshare_locked_value}\n" \
                           f"{info_dict['rshare_locked_pct']}%"
    image_editable.text((130,956), rshare_staked_text, (96, 96, 96), font=bit_bigger_font)
    image_editable.text((112,1000), rshare_staked_text_2, (106, 106, 106), font=title_font_bold)
    image_editable.text((280,1000), rshare_staked_text_3, (96, 96, 96), font=title_font)

    # RATES
    if float(info_dict['peg']) >= 1.01:
        rates_text = f"Boardroom Rates"
        rates_text_2 = f"APR:\n" \
                       f"Daily ROI:\n" \
                       f"Expansion:"
        rates_text_3 = f"{'{:0.2f}'.format(float(info_dict['boardroom_apr'])*365)}%\n" \
                       f"{info_dict['boardroom_apr']}%\n" \
                       f"{info_dict['expansion'] * 100}%"
        image_editable.text((590,956), rates_text, (96, 96, 96), font=bit_bigger_font)
        image_editable.text((580,1000), rates_text_2, (106, 106, 106), font=title_font_bold)
        image_editable.text((728,1000), rates_text_3, (96, 96, 96), font=title_font)
    else:
        rates_text_2 = f"TWAP x{info_dict['peg']}"
        rates_text = f"Available:  {info_dict['rbond_available']}"
        rates_text_3 = f"Boardroom Rewards Paused"
        image_editable.text((570,1010), rates_text, (96, 96, 96), font=price_font_small)
        image_editable.text((570,1045), rates_text_2, (84, 0, 0), font=smallest_font)
        image_editable.text((540,1070), rates_text_3, (146, 146, 146), font=title_font_bold)

    my_image.save(filepath_files+"/current_stats.png")