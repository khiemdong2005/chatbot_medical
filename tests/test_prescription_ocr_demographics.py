import os
import sys
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.reconciliation_service import reconcile_parallel_results

class TestPrescriptionDemographicsReconciliation(unittest.TestCase):
    def test_reconcile_quany175_prescription_demographics(self):
        """
        Kiểm tra khả năng bóc tách chính xác Tuổi (40), Giới tính (Nam),
        Bệnh viện Quân y 175 và Chẩn đoán bệnh kể cả khi OCR có lỗi chính tả.
        """
        raw_ocr_sample = (
            '"o Quoc runn6 .\n'
            'FKTYCS al hohhv | "evi Vifs Qlan >\n'
            'Khoa Dirvc | Nha thuoc 86 2 | 26109168\n'
            'ĐƠN THUÓC\n'
            'Iv Nni | Nâm sỉnb; 40 Tomt (im tIrh: ,am\n'
            'Dvtnne ?4 Khan Ihen )éu cu | pchi: | Ken | SpT:\n'
            'Sinh hou | M | Ls; 8Onule | M;828 | (phct | T:56400€ | Cx; 68 O0kg\n'
            'Chan dohn: Viêm rùi hrag cdp: HC\' Irão nguac đa d4g tkuc quan\n'
            'SLsinhdpchuoc: | 1. Althax | [KDNT] I20mg (7hwomntuiie) | Ionghy = 20 Vin\n'
            'Sang | cru:\n'
        )
        fake_ocr_data = {
            "success": True,
            "raw_text": raw_ocr_sample,
            "lines": [{"text": line} for line in raw_ocr_sample.split('\n') if line],
            "rows": []
        }

        reconciled = reconcile_parallel_results(fake_ocr_data, {}, doc_type="prescription")

        # 1. Tuổi & Năm sinh
        self.assertEqual(reconciled.get("age"), "40", "Tuổi phải là 40")
        self.assertIn("1986", str(reconciled.get("dob")), "Năm sinh phải tự động tính là 1986 (2026 - 40)")

        # 2. Giới tính
        self.assertEqual(reconciled.get("gender"), "Nam", "Giới tính phải được nhận diện chính xác là Nam")

        # 3. Cơ sở y tế
        self.assertEqual(reconciled.get("facility"), "Bệnh viện Quân y 175", "Bệnh viện phải là Bệnh viện Quân y 175")

        # 4. Chẩn đoán
        self.assertTrue(
            "Trào ngược dạ dày" in reconciled.get("diagnosis", "") or "Viêm mũi họng" in reconciled.get("diagnosis", ""),
            "Chẩn đoán phải chứa thông tin lâm sàng hợp lệ"
        )

if __name__ == '__main__':
    unittest.main()
