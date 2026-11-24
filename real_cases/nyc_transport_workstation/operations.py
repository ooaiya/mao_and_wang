"""Four TLC business operations. No task timing, pressure generation or scheduler."""
import argparse
import json
from pathlib import Path

ROOT = Path('/home/mxt/TeamOOM')
CASE = 'real_cases/nyc_transport_workstation'
ASSETS = ROOT / 'assets' / CASE
OUTPUT = ROOT / 'results' / CASE
COLUMNS = ['tpep_pickup_datetime', 'tpep_dropoff_datetime', 'trip_distance',
           'PULocationID', 'DOLocationID', 'fare_amount', 'total_amount']


def files():
    result = sorted((ASSETS / 'yellow_taxi').glob('yellow_tripdata_202[34]-??.parquet'))
    if len(result) != 24:
        raise ValueError('exactly 24 official monthly files required')
    return result


def batches(columns, selected=None):
    import pyarrow.parquet as pq
    for path in selected or files():
        for batch in pq.ParquetFile(path).iter_batches(batch_size=250000, columns=columns):
            yield path, batch.to_pandas()


def save(out, name, value):
    (out / name).write_text(json.dumps(value, indent=2, default=str))


def operation_a(out):
    import pandas as pd
    import matplotlib.pyplot as plt
    totals = {'hour': None, 'pickup': None, 'dropoff': None, 'distance': None, 'revenue': None, 'fare_distribution': None, 'revenue_distribution': None}
    n = 0
    for path, df in batches([c for c in COLUMNS if c != 'tpep_dropoff_datetime']):
        n += len(df)
        year = df.tpep_pickup_datetime.dt.year
        valid = df[year.between(2023, 2024)].copy()
        valid['year'] = valid.tpep_pickup_datetime.dt.year
        valid['hour'] = valid.tpep_pickup_datetime.dt.hour
        valid['distance_bin'] = pd.cut(valid.trip_distance, [0, 1, 3, 5, 10, 25, 100], include_lowest=True)
        valid['fare_bin']=pd.cut(valid.fare_amount,[0,5,10,20,50,100,500],include_lowest=True)
        valid['revenue_bin']=pd.cut(valid.total_amount,[0,5,10,20,50,100,500],include_lowest=True)
        groups = {'fare_distribution':valid.groupby(['year','fare_bin'],observed=True).size(), 'revenue_distribution':valid.groupby(['year','revenue_bin'],observed=True).size(), 'hour': valid.groupby(['year', 'hour']).size(),
                  'pickup': valid.groupby(['year', 'PULocationID']).size(),
                  'dropoff': valid.groupby(['year', 'DOLocationID']).size(),
                  'distance': valid.groupby(['year', 'distance_bin'], observed=True).size(),
                  'revenue': valid.groupby('year')[['fare_amount', 'total_amount']].agg(['sum', 'count'])}
        for key, series in groups.items():
            totals[key] = series if totals[key] is None else totals[key].add(series, fill_value=0)
    for name, series in totals.items():
        series.to_csv(out / (name + '_annual_summary.csv'))
    fig, ax = plt.subplots(figsize=(10, 5))
    totals['hour'].unstack(0).plot(ax=ax, title='NYC TLC trips by pickup hour and year')
    fig.savefig(out / 'annual_hourly_demand.png');plt.close(fig)
    save(out, 'analysis_summary.json', dict(operation='A',input_rows=n, input_files=24,
         method='Pandas batch aggregation of full official data; no sampling; pickup years outside 2023-2024 excluded from annual groups'))
    (out/'annual_analysis_report.md').write_text('# NYC TLC annual analysis\n\nFull 24-month inputs processed with Pandas. Hour, pickup/dropoff zone, distance and fare/revenue summaries accompany this report. Data are vendor-supplied and may contain invalid records. This is an independent business analysis, not an OOM or concurrency result.\n')


def operation_b(out):
    import duckdb
    con = duckdb.connect()
    paths = [str(p) for p in files()]
    con.read_parquet(paths, union_by_name=True).create_view('trips')
    queries = {
        'monthly_trip_summary.csv': "SELECT date_trunc('month', tpep_pickup_datetime) month, count(*) trips, avg(trip_distance) mean_distance, sum(fare_amount) fares, sum(total_amount) revenue FROM trips GROUP BY 1 ORDER BY 1",
        'zone_revenue_summary.csv': 'SELECT PULocationID pickup_zone, count(*) trips, avg(trip_distance) mean_distance, sum(total_amount) revenue FROM trips GROUP BY 1 ORDER BY 1',
        'hourly_demand_summary.csv': "SELECT date_trunc('month',tpep_pickup_datetime) month, extract(hour from tpep_pickup_datetime) hour, count(*) trips FROM trips GROUP BY 1,2 ORDER BY 1,2"}
    for name, query in queries.items():
        con.execute(query).df().to_csv(out/name,index=False)
    count = con.execute('SELECT count(*) FROM trips').fetchone()[0]
    save(out,'analysis_summary.json',dict(operation='B',input_rows=count, monthly_count_reconciled=True,
         note='grouped by actual pickup timestamps; out-of-month records retained and visible'))
    import pandas as pd
    assert int(pd.read_csv(out/'monthly_trip_summary.csv').trips.sum()) == count
    con.close()


def operation_c(out):
    import pandas as pd
    import geopandas as gpd
    import matplotlib.pyplot as plt
    od = None;n = 0
    for _, df in batches(['PULocationID','DOLocationID']):
        n += len(df);group = df.groupby(['PULocationID','DOLocationID'],dropna=False).size()
        od = group if od is None else od.add(group,fill_value=0)
    assert int(od.sum()) == n
    od.rename('trips').unstack(fill_value=0).to_csv(out/'taxi_od_matrix.csv')
    pickup = od.groupby(level=0,dropna=False).sum().rename('pickup_trips')
    dropoff = od.groupby(level=1,dropna=False).sum().rename('dropoff_trips')
    pickup.to_csv(out/'pickup_zone_analysis.csv');dropoff.to_csv(out/'dropoff_zone_analysis.csv')
    zones = gpd.read_file('/vsizip/' + str(ASSETS/'taxi_zones/taxi_zones.zip') + '/taxi_zones/taxi_zones.shp')
    lookup=pd.read_csv(ASSETS/'taxi_zones/taxi_zone_lookup.csv')
    assert lookup.LocationID.is_unique
    zones=zones.merge(lookup[['LocationID','service_zone']],on='LocationID',how='left')
    zones = zones.merge(pickup,left_on='LocationID',right_index=True,how='left').merge(dropoff,left_on='LocationID',right_index=True,how='left')
    assert zones.crs is not None and zones.geometry.notna().all()
    zones.to_file(out/'taxi_zone_analysis.gpkg',layer='zone_flow',driver='GPKG')
    assert len(gpd.read_file(out/'taxi_zone_analysis.gpkg',layer='zone_flow'))==len(zones)
    fig,ax=plt.subplots(figsize=(10,10));zones.plot(column='pickup_trips',ax=ax,legend=True)
    ax.set_title('NYC TLC pickup zone demand');fig.savefig(out/'zone_flow_map.png');plt.close(fig)
    save(out,'analysis_summary.json',dict(operation='C',input_rows=n,od_sum=int(od.sum()),zones=len(zones),
         unmatched_pickup_ids=[str(x) for x in pickup.index if x not in set(zones.LocationID)],
         note='Unknown/outside-NYC IDs retained in OD and CSV; not fabricated into geographic shapes'))


def features(df):
    import numpy as np
    pickup=df.tpep_pickup_datetime
    duration=(df.tpep_dropoff_datetime-pickup).dt.total_seconds()
    valid=duration.between(60,7200)&df.trip_distance.between(.01,100)&pickup.notna()&df.PULocationID.notna()&df.DOLocationID.notna()
    x=np.column_stack([df.trip_distance,df.PULocationID,df.DOLocationID,pickup.dt.hour,pickup.dt.dayofweek,pickup.dt.month]).astype('float32')
    valid=valid.to_numpy()&np.isfinite(x).all(axis=1)
    return x[valid],duration.to_numpy(dtype='float32')[valid],pickup.dt.year.to_numpy()[valid]


def operation_d(out):
    import numpy as np
    import pyarrow.parquet as pq
    import lightgbm as lgb
    import matplotlib.pyplot as plt
    from sklearn.metrics import mean_absolute_error,mean_squared_error
    # Disk-backed feature storage prevents retaining all Pandas frames/copies in RAM.
    capacity=sum(pq.ParquetFile(p).metadata.num_rows for p in files())
    arrays={split:(np.memmap(out/(split+'_features.dat'),dtype='float32',mode='w+',shape=(capacity,6)),
                   np.memmap(out/(split+'_target.dat'),dtype='float32',mode='w+',shape=(capacity,))) for split in ['train','test']}
    counts=dict(train=0,test=0);input_rows=0
    for _, df in batches(COLUMNS[:5]):
        input_rows+=len(df);x,y,years=features(df)
        for split,year in [('train',2023),('test',2024)]:
            mask=years==year;n=int(mask.sum());start=counts[split]
            arrays[split][0][start:start+n]=x[mask];arrays[split][1][start:start+n]=y[mask];counts[split]+=n
    assert min(counts.values())>0
    x,y=arrays['train'];n=counts['train']
    model=lgb.LGBMRegressor(n_estimators=100,num_leaves=31,learning_rate=.1,n_jobs=2,random_state=20261124,verbosity=-1)
    model.fit(x[:n],y[:n],feature_name=['trip_distance','pickup_zone','dropoff_zone','pickup_hour','weekday','month'])
    model.booster_.save_model(str(out/'trip_duration_model.txt'))
    loaded=lgb.Booster(model_file=str(out/'trip_duration_model.txt'))
    x,y=arrays['test'];n=counts['test'];absolute=squared=0.;points=[]
    for start in range(0,n,250000):
        end=min(start+250000,n);pred=loaded.predict(x[start:end],num_threads=2)
        absolute+=mean_absolute_error(y[start:end],pred)*(end-start)
        squared+=mean_squared_error(y[start:end],pred)*(end-start)
        if not points:points=[y[start:min(end,start+1000)].copy(),pred[:1000]]
    # Reload check compares identical real examples; dropoff time is label-only.
    assert np.allclose(loaded.predict(x[:100],num_threads=2),model.predict(x[:100]))
    import pandas as pd
    pd.DataFrame({'feature':loaded.feature_name(),'importance':loaded.feature_importance()}).to_csv(out/'feature_importance.csv',index=False)
    fig,ax=plt.subplots();ax.scatter(*points,s=3);ax.set_xlabel('Observed duration seconds');ax.set_ylabel('Predicted duration seconds');fig.savefig(out/'prediction_analysis.png');plt.close(fig)
    save(out,'model_metrics.json',dict(operation='D',input_rows=input_rows,train_year=2023,test_year=2024,valid_rows=counts,
         mae_seconds=absolute/n,rmse_seconds=(squared/n)**.5,model_reloaded=True,
         filters='60..7200 seconds duration, .01..100 miles, finite features; all other pickup years excluded',
         features=loaded.feature_name(),no_dropoff_feature=True,parameters=model.get_params()))


def run(operation):
    out=OUTPUT/('operation_'+operation);out.mkdir(parents=True,exist_ok=True)
    globals()['operation_'+operation.lower()](out)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=list('ABCD'));args=parser.parse_args();run(args.operation)
