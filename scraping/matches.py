import math
import pandas as pd
import numpy as numpy
import jellyfish
import datetime
import time
import sys
import os


RACE_DICT = {}


D = {"CH": "Chicago", "NY":"NewYork", "BS":"Boston"}
for city in D.keys():
    for year in range(14,20):
        RACE_ID = city + str(year)
        full_name = D[city]
        full_year = "20" + str(year)
        RACE_DICT[RACE_ID] = [
        full_name + full_year + "official.csv", "strava_" + full_name.lower() + "_" + full_year + ".csv"]


def create_marathon_df(raceID):
    '''
    Takes in the csv file of a race's results scraped from the marathon website and turns it into a useable dataframe object

    Inputs:
        filename (string) name of the file we want to turn into a df
    Returns:
        marathon_df (DataFrame) 
    '''
    print(RACE_DICT[raceID][0])
    filename = "race_result/" + RACE_DICT[raceID][0] #need to standardize these names

    marathon_df = pd.read_csv(filename, header=None) 
    #read without a header because the first row of csv contains real data
    marathon_df.columns = ['Name', 'Gender_and_Age', 'Time']

    # Some official results from marathonguide.com are capitalized
    # We need to adjust the format so that the Jaro-Winkler algorithms 
    # won't give us 0 scores. 
    name = marathon_df.iloc[1,0]
    if name.isupper():
        f = lambda s: s.title()
        marathon_df["Name"] = marathon_df["Name"].apply(f)
    

    marathon_df['Gender'] = marathon_df['Gender_and_Age'].str[0]
    marathon_df['Age'] = marathon_df['Gender_and_Age'].str[1:]
    marathon_df['RaceID'] = raceID
    marathon_df['Age_Lower'] = marathon_df['Age'].str.extract('(\d+)-')
    marathon_df['Age_Upper'] = marathon_df['Age'].str.extract('-(\d+)')
    marathon_df = marathon_df.drop(columns=['Gender_and_Age', 'Age'])

    marathon_df = convert_to_seconds(marathon_df)

    marathon_df.columns = [
    'm_Name', 'm_Time', 'm_Gender', 'm_RaceID', 'm_Age_Lower', 'm_Age_Upper']
    marathon_df['m_Age_Lower'].fillna(0, inplace=True)
    marathon_df['m_Age_Upper'].fillna(120, inplace=True)
    marathon_df = marathon_df.astype({
        'm_Age_Lower': 'int64', 'm_Age_Upper': 'int64'})


    print(marathon_df)
    return marathon_df

def create_strava_df(raceID):
    '''
    Takes in the csv file of a race's results scraped from strava and turns it into a useable dataframe objects.

    Inputs:
        filename (string) name of the file we want to turn into a df
    Returns:
        strava_df_list (list) list of DataFrame objects 
    '''

    filename = "race_result/" + RACE_DICT[raceID][1]

    strava_df = pd.read_csv(filename, sep='|')
    strava_df['Time'] = strava_df['Time1']
    strava_df = strava_df.drop(columns=['Time1', 'Time2'])
    strava_df = strava_df[strava_df['Time'].str.contains("^\d:")]

    strava_df = convert_to_seconds(strava_df)
    strava_df['Age_Lower'] = strava_df['Age'].str.extract('(\d+)-')
    strava_df['Age_Upper'] = strava_df['Age'].str.extract('-(\d+)')
    #strava_df = strava_df[strava_df['Shoes'].isna() == False]

    strava_df = strava_df.drop(columns=['Age'])
    strava_df.columns = [
    's_RaceID','s_Name', 's_Gender', 's_Shoes', 's_Time',  's_Age_Lower', 's_Age_Upper']

    strava_df['s_Age_Lower'].fillna(0, inplace=True)
    strava_df['s_Age_Upper'].fillna(120, inplace=True)
    strava_df = strava_df.astype(
        {'s_Age_Lower': 'int64', 's_Age_Upper': 'int64'})

    return strava_df

def convert_to_seconds(df):
    '''
    Take in df and return it with the time column converted to seconds
    '''
    df['Time'] = df.apply(
        lambda row: time.strptime(row.loc['Time'], '%H:%M:%S'), axis=1)
    df['Time'] = df.apply(
        lambda row: row.loc['Time'].tm_hour * 3600 + row.loc['Time'].tm_min * 60 + row.loc['Time'].tm_sec, axis=1)

    return df

def create_matches(raceID, acceptable_name_score=0.85):
    '''
    Takes in a race ID and returns a dataframe of acceptable matches based on a passed acceptable time difference score and an acceptable namedifference score

    Inputs:
        raceID: (str) ID of the race you'd like to get matches for
        acceptable_time_diff (int) difference in seconds that you'd still consider a match
        acceptable_name_diff (int) Between 0-1, acceptable jaro-winkler score
    Returns:
        matches (DataFrame)
    '''

    marathon_df = create_marathon_df(raceID)
    strava_df = create_strava_df(raceID)

    s_match_indexes = []
    m_match_indexes = []

    for s_index, s_row in strava_df.iterrows():
        strava_time = s_row.at['s_Time']
        strava_name = s_row.at['s_Name']
        strava_gender = s_row.at['s_Gender']
        strava_age_lower = s_row.at['s_Age_Lower']
        strava_age_upper = s_row.at['s_Age_Upper']


        searchable_marathon_df = marathon_df[(
            marathon_df['m_Time'] <= strava_time + 60) & (marathon_df['m_Time'] >= strava_time - 60) & (marathon_df['m_Gender'] == strava_gender)]
        print(s_index)
        for m_index, m_row in searchable_marathon_df.iterrows():
            marathon_age_lower = m_row.at['m_Age_Lower']
            marathon_age_upper = m_row.at['m_Age_Upper']
            # if strava_age_present:
            #     marathon_age_lower = int(marathon_age_lower)
            #     marathon_age_upper = int(marathon_age_upper)
            if marathon_age_lower >= strava_age_upper or strava_age_lower >= marathon_age_upper:
                continue

            # print('s_index:', s_index, 'm_index:', m_index)
            marathon_name = m_row.at['m_Name']

            name_score = jellyfish.jaro_winkler(strava_name, marathon_name)
            if name_score >= acceptable_name_score:
                s_match_indexes.append(s_index)
                m_match_indexes.append(m_index)
                break

    matches = pd.concat([strava_df.loc[s_match_indexes].reset_index(drop=True), marathon_df.loc[m_match_indexes].reset_index(drop=True)], axis=1)
    
    matches['Age_Lower'] = matches[['s_Age_Lower', 'm_Age_Lower']].max(axis=1)
    matches['Age_Upper'] = matches[['s_Age_Upper', 'm_Age_Upper']].min(axis=1)

    matches = matches.drop(columns=['s_Time','s_RaceID', 's_Name', 's_Gender', 's_Age_Lower', 's_Age_Upper', 'm_Age_Lower', 'm_Age_Upper'])
    matches.columns = ['Shoes', 'Name', 'Time', 'Gender', 'RaceID', 'Age_Lower', 'Age_Upper']
    new_columns = ['RaceID', 'Name', 'Time', 'Gender', 'Age_Lower', 'Age_Upper', 'Shoes']
    matches = matches[new_columns]

    return matches


def go(raceID):
    '''
    This function trims the data for each race, combine them, and write them
    to a sql database table
    '''

    df = create_matches(raceID, 0.85)
    if not os.path.exists("race_result/master_matches.csv"):
        df.to_csv("race_result/master_matches.csv",index=False,mode='w')
    else:
        df.to_csv("race_result/master_matches.csv",index=False,mode='a',header=False)



if __name__ == "__main__":
    raceID = sys.argv[1]
    go(raceID)