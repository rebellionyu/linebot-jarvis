#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
from urllib.request import urlopen
from configparser import ConfigParser
import os
import json
from fuzzywuzzy import process


def getWeather(query):
    # preprocess
    # replace 台 to 臺
    query[0] = query[0].replace('台', '臺')
    query[1] = query[1].replace('台', '臺')

    # get weather
    # load county code file
    parDir = os.path.dirname(os.path.abspath(__file__))
    conf = json.load(open(os.path.join(parDir, 'distInfo.json'), 'r', encoding='utf8'))

    # approximate matching
    query[0] = process.extractOne(query[0], conf.keys())[0]
    query[1] = process.extractOne(query[1], conf[query[0]].keys())[0]
    countyCode = conf[query[0]][query[1]][0]


    # get 3 hours result
    rawData = (urlopen('http://www.cwb.gov.tw/V7/forecast/town368/3Hr/{countyCode}.htm'.
            format(countyCode=countyCode)))
    soup = BeautifulSoup(rawData, 'html.parser')
    threeHour = soup.find_all('tr')

    # get 7 days result
    rawData = (urlopen('http://www.cwb.gov.tw/V7/forecast/town368/7Day/{countyCode}.htm'.
            format(countyCode=countyCode)))
    soup = BeautifulSoup(rawData, 'html.parser')
    sevenDay = soup.find_all('tr')
    
    # parse data
    # three hours
    # date: 0, time: 1, temperature: 3, rainfall prob.: 8
    # seven days
    # date: 0, time: 1, high temp: 3, low temp: 4, condition: 2
    getColspan = lambda col: int(col) if col else 1
    ceil = lambda num: int(num/2)+1 if num%2 != 0 else int(num/2)
    soupDate = threeHour[0].find_all('td', limit=3)[1:]
    tmpSeven = sevenDay[0].find_all('td')[1:]
    if soupDate[0].get_text()[-1] == tmpSeven[0].get_text()[-1]:
        soupDate += tmpSeven[2:]
        ran = 5
    else:
        soupDate += tmpSeven[1:6]
        ran = 3
    
    # collect date and numCol
    res = []
    for day in soupDate:
        res.append({'numCol': getColspan(day.get('colspan')),
                    'date': day.get_text(),
                    'time': [],
                    'temp': [],
                    'condition': []})
    
    # get the result we want
    tmpRange = getColspan(soupDate[0].get('colspan')) + getColspan(soupDate[1].get('colspan'))
    soupTime = threeHour[1].find_all('td')[1:(1+tmpRange)] + sevenDay[1].find_all('td')[ran:ran+10]
    soupTemp = threeHour[3].find_all('td')[1:(1+tmpRange)]
    soupRain = threeHour[8].find_all('td')[1:1+ceil(tmpRange)]
    soupHighTemp = sevenDay[3].find_all('td')[ran:ran+10]
    soupLowTemp = sevenDay[4].find_all('td')[ran:ran+10]
    soupCond = sevenDay[2].find_all('img')[ran-1:ran+9]

    
    # comb the result
    # forecast time
    forecastTime = [t.get_text() for t in soupTime]

    # duplicate rainfall probability
    cond = []
    for r in soupRain:
        if r.get('colspan'):
            cond.extend([r.get_text(), r.get_text()])
        else:
            cond.append(r.get_text())
    cond.extend([c['title'] for c in soupCond])

    # concatenate temp
    temp = [t.get_text() for t in soupTemp]
    temp.extend(['{}~{}'.format(lTemp.get_text(), hTemp.get_text()) \
                    for lTemp, hTemp in zip(soupLowTemp, soupHighTemp)])
    # collect data
    start = 0
    for dayIdx in range(7):
        end = start+res[dayIdx]['numCol']
        res[dayIdx]['time'].extend(forecastTime[start:end])
        res[dayIdx]['temp'].extend(temp[start:end])
        res[dayIdx]['condition'].extend(cond[start:end])
        start += res[dayIdx]['numCol']


    # get AQI
    # http://taqm.epa.gov.tw/taqm/aqs.ashx?lang=tw&act=aqi-epa
    rawData = urlopen('http://taqm.epa.gov.tw/taqm/aqs.ashx?lang=tw&act=aqi-epa')
    stationID = int(conf[query[0]][query[1]][1])
    aqiData = json.loads(rawData.read().decode('utf8'))['Data']
    res.append({'aqiStyle': aqiData[stationID]['AQIStyle'],
                'site': aqiData[stationID]['SiteName']})

    if res[-1]['aqiStyle'] == 'AQI0':
        res[-1]['aqiStyle'] = '設備維護'
    elif res[-1]['aqiStyle'] == 'AQI1':
        res[-1]['aqiStyle'] = '良好'
    elif res[-1]['aqiStyle'] == 'AQI2':
        res[-1]['aqiStyle'] = '普通'
    elif res[-1]['aqiStyle'] == 'AQI3':
        res[-1]['aqiStyle'] = '對敏感族群不健康'
    elif res[-1]['aqiStyle'] == 'AQI4':
        res[-1]['aqiStyle'] = '對所有族群不健康'
    elif res[-1]['aqiStyle'] == 'AQI5':
        res[-1]['aqiStyle'] = '非常不健康'
    elif res[-1]['aqiStyle'] == 'AQI6':
        res[-1]['aqiStyle'] = '危害'

    # typesetting result
    # aqi result
    display = ('{queryDist}\n'
                '空氣品質: \n'
                '    觀測站: {site}\n'
                #'    AQI: {aqi}\n'
                '    空氣品質指標: {quality}\n'
                .format(queryDist=' '.join(query), site=res[-1]['site'], quality=res[-1]['aqiStyle']))
    # weather result
    # precise prediction
    for dayIdx in range(2):
        display += ('{D}\n'
                    '    時間    溫度     降雨機率\n'
                    .format(D='{} {}'.format(res[dayIdx]['date'][:5], res[dayIdx]['date'][5:])))
        for time, temp, rain in (zip(res[dayIdx]['time'], 
                                    res[dayIdx]['temp'], 
                                    res[dayIdx]['condition'])):
            display += ('    {TIME}   {TEMP}       {RAIN}\n'
                        .format(TIME=time, TEMP=temp, RAIN=rain))
    # rough prediction
    for dayIdx in range(2, 7):
        display += ('{D}\n'
                    #'    時間    溫度   天氣狀況\n'
                    .format(D='{} {}'.format(res[dayIdx]['date'][:5], res[dayIdx]['date'][5:])))
        for time, temp, cond in (zip(res[dayIdx]['time'], 
                                    res[dayIdx]['temp'], 
                                    res[dayIdx]['condition'])):
            display += ('    {TIME}    {TEMP}    {COND}\n'
                        .format(TIME=time, TEMP=temp, COND=cond))
    return display


if __name__ == '__main__':
    query = ['台中', '豐原市']
    print(getWeather(query))
