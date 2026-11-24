"""Tiny feature-contract fixtures, never empirical taxi records or profiles."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

spec=importlib.util.spec_from_file_location('nyc_operations',Path(__file__).resolve().parents[1]/'real_cases/nyc_transport_workstation/operations.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class FeaturesTests(unittest.TestCase):
    def frame(self):
        pickup=pd.to_datetime(['2023-01-01 10:00','2024-01-01 11:00','2024-01-01 12:00'])
        return pd.DataFrame(dict(tpep_pickup_datetime=pickup,tpep_dropoff_datetime=pickup+pd.to_timedelta([120,240,10],unit='s'),trip_distance=[1.,2.,3.],PULocationID=[1,2,3],DOLocationID=[2,3,4]))
    def test_filters_and_year_split(self):
        x,y,years=module.features(self.frame());self.assertEqual(x.shape,(2,6));np.testing.assert_equal(years,[2023,2024]);np.testing.assert_equal(y,[120,240])
    def test_dropoff_changes_labels_only(self):
        df=self.frame();x,y,_=module.features(df);df.tpep_dropoff_datetime+=pd.Timedelta(seconds=30);other,target,_=module.features(df);np.testing.assert_equal(x,other[:2]);np.testing.assert_equal(target[:2],y+30)
    def test_nonfinite_features_rejected(self):
        df=self.frame();df.loc[0,'trip_distance']=np.inf;x,y,_=module.features(df);self.assertEqual(len(y),1)
