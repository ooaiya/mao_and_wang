import unittest
from independent_plan import value,envelope,align

class CurveTests(unittest.TestCase):
    def test_roundoff_is_not_an_unobserved_tail(self):
        c=[(0.,10.),(.1,20.)]
        self.assertEqual(value(c,.1+1e-12),20.)
        self.assertIsNone(value(c,.2))
    def test_terminal_charge_is_retained(self):
        m=envelope([(0,10),(.5,100),(1,30)],2,25,tail_bound=150,factor=1)
        self.assertIn([1500,150],m['curve'])
        self.assertEqual(m['curve'][-1],[2000,25])
    def test_upper_envelope_preserves_short_peak(self):
        m=envelope([(0,1),(.11,100),(.12,1),(1,1)],1,1,factor=1)
        self.assertEqual(m['curve'][0],[0,100])

if __name__=='__main__':unittest.main()
