.PHONY: install-service uninstall-service install-udev uninstall-udev

install-service:
	sudo cp contrib/k70-volume-filter.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable --now k70-volume-filter

uninstall-service:
	sudo systemctl disable --now k70-volume-filter || true
	sudo rm -f /etc/systemd/system/k70-volume-filter.service
	sudo systemctl daemon-reload

install-udev:
	sudo cp contrib/99-k70-volume-filter.rules /etc/udev/rules.d/
	sudo udevadm control --reload-rules
	sudo udevadm trigger

uninstall-udev:
	sudo rm -f /etc/udev/rules.d/99-k70-volume-filter.rules
	sudo udevadm control --reload-rules
